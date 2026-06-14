"""OIDC wired into both surfaces (ADR 0013, M4 slice 3).

REST: the bearer dependency verifies + maps a token to the principal. MCP: the
mount gets a RemoteAuthProvider, and the tool middleware resolves the principal
from the verified token. Dev mode is unchanged (covered elsewhere).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from afs_core.errors import UnauthenticatedError
from afs_server.app import create_app
from afs_server.auth import build_resource_auth, build_token_verifier
from afs_server.dependencies import get_settings
from afs_server.settings import Settings
from afs_server.tools import ToolMiddleware

ISSUER = "https://issuer.test"
AUDIENCE = "agentic-fs"


@pytest.fixture(scope="module")
def keypair() -> RSAKeyPair:
    return RSAKeyPair.generate()


def _oidc_settings(keypair: RSAKeyPair, **over: object) -> Settings:
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


# --- REST surface -------------------------------------------------------------


@pytest.fixture
def rest(keypair: RSAKeyPair) -> Iterator[TestClient]:
    settings = _oidc_settings(keypair)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        c.app.state.token_verifier = build_token_verifier(settings)
        yield c


def test_rest_valid_token_maps_principal(rest: TestClient, keypair: RSAKeyPair) -> None:
    r = rest.get("/v1/me", headers={"Authorization": f"Bearer {_token(keypair)}"})
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "acme"
    assert body["principal_id"] == "alice"
    assert body["scopes"] == ["fs:read"]
    assert body["namespaces"] == ["handbook"]


def test_rest_missing_token_is_401(rest: TestClient) -> None:
    assert rest.get("/v1/me").status_code == 401


def test_rest_forged_token_is_401(rest: TestClient) -> None:
    attacker = RSAKeyPair.generate()
    forged = attacker.create_token(
        subject="mallory",
        issuer=ISSUER,
        audience=AUDIENCE,
        scopes=["admin"],
        additional_claims={"tenant_id": "acme"},
    )
    r = rest.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_rest_healthz_is_open(rest: TestClient) -> None:
    assert rest.get("/v1/healthz").status_code == 200  # liveness needs no token


# --- MCP surface --------------------------------------------------------------


def test_build_resource_auth_dev_is_none() -> None:
    assert build_resource_auth(Settings(auth_mode="dev"), None) is None


def test_build_resource_auth_oidc_returns_provider(keypair: RSAKeyPair) -> None:
    settings = _oidc_settings(keypair)
    provider = build_resource_auth(settings, build_token_verifier(settings))
    assert provider is not None  # a RemoteAuthProvider (serves RFC 9728 metadata)


def test_build_resource_auth_oidc_without_issuer_fails(keypair: RSAKeyPair) -> None:
    settings = _oidc_settings(keypair, oidc_issuer=None)
    with pytest.raises(UnauthenticatedError, match="AFS_OIDC_ISSUER"):
        build_resource_auth(settings, build_token_verifier(settings))


def test_mcp_middleware_principal_from_token(monkeypatch, keypair: RSAKeyPair) -> None:
    mw = ToolMiddleware({}, _oidc_settings(keypair))
    fake = AccessToken(
        token="x",
        client_id="c",
        scopes=["fs:read"],
        claims={"sub": "u", "tenant_id": "acme", "scope": "fs:read", "afs_namespaces": ["h"]},
    )
    monkeypatch.setattr("fastmcp.server.dependencies.get_access_token", lambda: fake)
    ctx = mw._principal()
    assert ctx.tenant_id == "acme"
    assert ctx.scopes == frozenset({"fs:read"})
    assert ctx.namespaces == frozenset({"h"})


def test_mcp_middleware_unauthenticated_fails_closed(monkeypatch, keypair: RSAKeyPair) -> None:
    mw = ToolMiddleware({}, _oidc_settings(keypair))
    monkeypatch.setattr("fastmcp.server.dependencies.get_access_token", lambda: None)
    with pytest.raises(UnauthenticatedError):
        mw._principal()


def test_mcp_middleware_dev_principal() -> None:
    mw = ToolMiddleware({}, Settings(auth_mode="dev"))
    assert mw._principal().tenant_id == "dev"
