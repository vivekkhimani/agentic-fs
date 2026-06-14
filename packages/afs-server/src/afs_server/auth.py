"""Authentication → a resolved tenant context.

Two modes (``AFS_AUTH_MODE``):

- **dev** — a static local principal. Loud, intentional, never production.
- **oidc** — an OAuth 2.1 **resource server** (ADR 0013): validate a bearer JWT
  against your own IdP's keys (JWKS or a static public key) and map its claims to
  a :class:`TenantContext`. We *validate* tokens; we never issue them ("bring your
  own IdP"). The crypto (signature / ``iss`` / ``aud`` / ``exp``) is delegated to
  FastMCP's ``JWTVerifier``; the only thing we own is the claim → context mapping.

Any unknown mode fails closed (401), so a misconfigured deployment never silently
serves data with no identity. No tokens or secrets are baked into the image.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from afs_core.errors import InsufficientScopeError, UnauthenticatedError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastmcp.server.auth import TokenVerifier

    from afs_server.settings import Settings

logger = logging.getLogger("afs_server.auth")

# Full scope set — granted to the dev principal only.
_ALL_SCOPES = frozenset({"fs:read", "fs:search", "fs:write:scratch", "ingest", "admin"})


@dataclass(frozen=True)
class TenantContext:
    """The authority resolved from a request: who, in which tenant, with what."""

    tenant_id: str
    principal_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    # None = all namespaces in the tenant are granted (dev convenience).
    namespaces: frozenset[str] | None = None

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise InsufficientScopeError(f"missing required scope: {scope}")

    def allows_namespace(self, namespace: str) -> bool:
        return self.namespaces is None or namespace in self.namespaces


_dev_warned = False


def resolve_dev_context(settings: Settings) -> TenantContext:
    """The static dev principal. Loud, intentional, never production."""
    global _dev_warned
    if not _dev_warned:
        logger.warning(
            "AFS_AUTH_MODE=dev — serving with a STATIC dev principal and no token "
            "verification. Never run this in production."
        )
        _dev_warned = True
    return TenantContext(
        tenant_id=settings.dev_tenant_id,
        principal_id=settings.dev_principal_id,
        scopes=_ALL_SCOPES,
        namespaces=None,
    )


def resolve_context(settings: Settings) -> TenantContext:
    if settings.auth_mode == "dev":
        return resolve_dev_context(settings)
    # oidc is request-scoped (the principal comes from the bearer token) and is
    # wired into the REST + MCP request paths in the next slice. Calling the
    # request-less resolver under oidc is a programming error, so fail closed.
    raise UnauthenticatedError(
        f"auth_mode {settings.auth_mode!r} resolves per request from a bearer token; "
        "use the request-scoped path, not resolve_context(settings)"
    )


# --- OIDC resource server (ADR 0013) ------------------------------------------


def build_token_verifier(settings: Settings) -> TokenVerifier | None:
    """A FastMCP ``TokenVerifier`` for ``auth_mode='oidc'`` (``None`` for dev).

    One verifier object is reused by both surfaces — the MCP mount (via
    ``RemoteAuthProvider``) and the REST bearer dependency — so there is a single
    validation path. Accepts a static PEM public key (offline "static-jwt" mode)
    or a JWKS URI / issuer; ``audience`` enforces RFC 8707 resource binding.
    """
    if settings.auth_mode != "oidc":
        return None
    if not (settings.oidc_public_key or settings.oidc_jwks_uri or settings.oidc_issuer):
        raise UnauthenticatedError(
            "auth_mode='oidc' needs one of AFS_OIDC_PUBLIC_KEY, AFS_OIDC_JWKS_URI, "
            "or AFS_OIDC_ISSUER"
        )
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    return JWTVerifier(
        public_key=settings.oidc_public_key,
        jwks_uri=settings.oidc_jwks_uri,
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        algorithm=settings.oidc_algorithm,
    )


def _scope_set(value: object) -> frozenset[str]:
    """Scopes are trusted from the token: a space-delimited string or a list."""
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, (list, tuple, set)):
        return frozenset(str(v) for v in value)
    raise UnauthenticatedError(f"unexpected scopes claim type: {type(value).__name__}")


def _namespace_set(value: object) -> frozenset[str] | None:
    """Granted namespaces: a list, or a comma/space-delimited string. Absent
    (``None``) means tenant-wide — ``tenant_id`` still isolates and scopes still
    gate, so this is a deliberate, documented default, not an open door."""
    if value is None:
        return None
    if isinstance(value, str):
        return frozenset(p for p in re.split(r"[,\s]+", value) if p)
    if isinstance(value, (list, tuple, set)):
        return frozenset(str(v) for v in value)
    raise UnauthenticatedError(f"unexpected namespaces claim type: {type(value).__name__}")


def context_from_claims(claims: Mapping[str, Any], settings: Settings) -> TenantContext:
    """Map a *validated* token's claims to a :class:`TenantContext` (ADR 0013).

    The token is assumed already verified (signature/iss/aud/exp) by the
    ``TokenVerifier``; this is the pure claim → authority mapping we own.
    """
    principal = claims.get(settings.oidc_principal_claim) or claims.get("sub")
    if not principal:
        raise UnauthenticatedError(
            f"token missing principal claim {settings.oidc_principal_claim!r}"
        )
    tenant = claims.get(settings.oidc_tenant_claim) or settings.oidc_default_tenant
    if not tenant:
        raise UnauthenticatedError(
            f"token missing tenant claim {settings.oidc_tenant_claim!r} and no "
            "AFS_OIDC_DEFAULT_TENANT fallback is set"
        )
    return TenantContext(
        tenant_id=str(tenant),
        principal_id=str(principal),
        scopes=_scope_set(claims.get(settings.oidc_scopes_claim)),
        namespaces=_namespace_set(claims.get(settings.oidc_namespaces_claim)),
    )
