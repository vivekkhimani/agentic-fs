"""`afs auth doctor` — the IdP-wiring diagnostic (ADR 0013)."""

from __future__ import annotations

import io

import pytest
from click.testing import CliRunner
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from afs_server.cli import main, run_doctor
from afs_server.settings import Settings

ISSUER = "https://issuer.test"
AUDIENCE = "agentic-fs"


@pytest.fixture(scope="module")
def keypair() -> RSAKeyPair:
    return RSAKeyPair.generate()


def _oidc(keypair: RSAKeyPair, **over: object) -> Settings:
    base: dict[str, object] = dict(
        auth_mode="oidc",
        oidc_public_key=keypair.public_key,
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
    )
    base.update(over)
    return Settings(**base)


def _token(keypair: RSAKeyPair, **claims: object) -> str:
    return keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience=AUDIENCE,
        scopes=["fs:read"],
        additional_claims={"tenant_id": "acme", "afs_namespaces": ["handbook"], **claims},
    )


def _run(settings: Settings, token: str | None) -> tuple[int, str]:
    buf = io.StringIO()
    code = run_doctor(settings, token, buf)
    return code, buf.getvalue()


def test_dev_mode_shows_static_principal() -> None:
    code, out = _run(Settings(auth_mode="dev"), None)
    assert code == 0
    assert "dev mode" in out
    assert "principal_id=dev" in out


def test_valid_token_passes_and_maps(keypair: RSAKeyPair) -> None:
    code, out = _run(_oidc(keypair), _token(keypair))
    assert code == 0
    assert "Verification: PASS" in out
    assert "tenant_id:    acme" in out
    assert "fs:read" in out
    assert "handbook" in out


def test_expired_token_fails_with_hint(keypair: RSAKeyPair) -> None:
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience=AUDIENCE,
        scopes=["fs:read"],
        additional_claims={"tenant_id": "acme"},
        expires_in_seconds=-10,
    )
    code, out = _run(_oidc(keypair), token)
    assert code == 1
    assert "FAIL" in out and "expired" in out


def test_wrong_audience_fails_with_hint(keypair: RSAKeyPair) -> None:
    code, out = _run(_oidc(keypair, oidc_audience="someone-else"), _token(keypair))
    assert code == 1
    assert "audience mismatch" in out


def test_deny_all_namespaces_is_flagged(keypair: RSAKeyPair) -> None:
    # token with no namespaces claim, server has no default → deny-all
    token = keypair.create_token(
        subject="alice",
        issuer=ISSUER,
        audience=AUDIENCE,
        scopes=["fs:read"],
        additional_claims={"tenant_id": "acme"},
    )
    code, out = _run(_oidc(keypair), token)
    assert code == 0
    assert "DENY-ALL" in out


def test_oidc_without_token_explains(keypair: RSAKeyPair) -> None:
    code, out = _run(_oidc(keypair), None)
    assert code == 2
    assert "no token provided" in out


def test_cli_invocation_dev(monkeypatch) -> None:
    monkeypatch.setenv("AFS_AUTH_MODE", "dev")
    result = CliRunner().invoke(main, ["auth", "doctor"])
    assert result.exit_code == 0
    assert "dev mode" in result.output
