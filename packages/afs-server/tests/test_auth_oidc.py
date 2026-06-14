"""OIDC resource-server verifier + claims mapping (ADR 0013, M4 slice 2).

Tokens are minted with a local RSA keypair and validated against its public key
(the "static-jwt" path) — the full verify → map flow with no live IdP, so CI is
hermetic.
"""

from __future__ import annotations

import pytest
from fastmcp.server.auth.providers.jwt import RSAKeyPair

from afs_core.errors import UnauthenticatedError
from afs_server.auth import build_token_verifier, context_from_claims
from afs_server.settings import Settings

ISSUER = "https://issuer.test"
AUDIENCE = "agentic-fs"


@pytest.fixture(scope="module")
def keypair() -> RSAKeyPair:
    return RSAKeyPair.generate()


def _settings(keypair: RSAKeyPair, **over: object) -> Settings:
    base: dict[str, object] = dict(
        auth_mode="oidc",
        oidc_public_key=keypair.public_key,
        oidc_issuer=ISSUER,
        oidc_audience=AUDIENCE,
    )
    base.update(over)
    return Settings(**base)


def _mint(keypair: RSAKeyPair, **claims: object) -> str:
    extra = dict(claims)
    scopes = extra.pop("scopes", ["fs:read"])
    return keypair.create_token(
        subject=str(extra.pop("subject", "user-1")),
        issuer=ISSUER,
        audience=AUDIENCE,
        scopes=scopes,  # type: ignore[arg-type]
        additional_claims=extra or None,
        expires_in_seconds=int(claims.get("expires_in_seconds", 3600)),  # type: ignore[arg-type]
    )


async def test_valid_token_maps_to_context(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    token = _mint(
        keypair,
        subject="alice",
        scopes=["fs:read", "ingest"],
        tenant_id="acme",
        afs_namespaces=["handbook", "eng"],
    )
    at = await build_token_verifier(settings).verify_token(token)
    assert at is not None  # signature/iss/aud/exp all passed

    ctx = context_from_claims(at.claims, settings)
    assert ctx.principal_id == "alice"
    assert ctx.tenant_id == "acme"
    assert ctx.scopes == frozenset({"fs:read", "ingest"})
    assert ctx.namespaces == frozenset({"handbook", "eng"})


async def test_absent_namespaces_claim_is_tenant_wide(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    ctx = context_from_claims({"sub": "u", "tenant_id": "acme", "scope": "fs:read"}, settings)
    assert ctx.namespaces is None  # tenant-wide; tenant_id still isolates


def test_scopes_accept_string_or_list(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    as_str = context_from_claims(
        {"sub": "u", "tenant_id": "t", "scope": "fs:read fs:search"}, settings
    )
    as_list = context_from_claims(
        {"sub": "u", "tenant_id": "t", "scope": ["fs:read", "fs:search"]}, settings
    )
    assert as_str.scopes == as_list.scopes == frozenset({"fs:read", "fs:search"})


def test_namespaces_accept_delimited_string(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    ctx = context_from_claims(
        {"sub": "u", "tenant_id": "t", "scope": "fs:read", "afs_namespaces": "a, b c"}, settings
    )
    assert ctx.namespaces == frozenset({"a", "b", "c"})


def test_configurable_claim_names(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair, oidc_tenant_claim="org_id", oidc_scopes_claim="scp")
    ctx = context_from_claims({"sub": "u", "org_id": "workos-org", "scp": ["fs:read"]}, settings)
    assert ctx.tenant_id == "workos-org"
    assert ctx.scopes == frozenset({"fs:read"})


def test_missing_tenant_claim_fails_closed(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    with pytest.raises(UnauthenticatedError, match="tenant"):
        context_from_claims({"sub": "u", "scope": "fs:read"}, settings)


def test_default_tenant_fallback(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair, oidc_default_tenant="solo")
    ctx = context_from_claims({"sub": "u", "scope": "fs:read"}, settings)
    assert ctx.tenant_id == "solo"


def test_missing_principal_claim_fails_closed(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    with pytest.raises(UnauthenticatedError, match="principal"):
        context_from_claims({"tenant_id": "t", "scope": "fs:read"}, settings)


async def test_wrong_audience_is_rejected(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair, oidc_audience="someone-else")
    token = _mint(keypair, tenant_id="acme")  # aud=AUDIENCE, but verifier wants someone-else
    assert await build_token_verifier(settings).verify_token(token) is None


async def test_expired_token_is_rejected(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    token = _mint(keypair, tenant_id="acme", expires_in_seconds=-10)
    assert await build_token_verifier(settings).verify_token(token) is None


async def test_token_from_another_key_is_rejected(keypair: RSAKeyPair) -> None:
    settings = _settings(keypair)
    attacker = RSAKeyPair.generate()
    forged = attacker.create_token(
        subject="mallory",
        issuer=ISSUER,
        audience=AUDIENCE,
        scopes=["admin"],
        additional_claims={"tenant_id": "acme"},
    )
    assert await build_token_verifier(settings).verify_token(forged) is None


def test_dev_mode_has_no_verifier() -> None:
    assert build_token_verifier(Settings(auth_mode="dev")) is None


def test_oidc_without_key_config_fails_closed() -> None:
    with pytest.raises(UnauthenticatedError, match="AFS_OIDC"):
        build_token_verifier(Settings(auth_mode="oidc"))
