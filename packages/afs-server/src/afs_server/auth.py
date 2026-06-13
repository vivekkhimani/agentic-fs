"""Authentication → a resolved tenant context.

This slice ships **dev auth only**: a static local principal selected when
``AFS_AUTH_MODE=dev``. Any other mode fails closed (401) until the OAuth 2.1
resource server lands — so a misconfigured deployment never silently serves data
with no identity. No tokens or secrets are baked into the image.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from afs_core.errors import InsufficientScopeError, UnauthenticatedError

if TYPE_CHECKING:
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
    # oidc and anything else: not implemented yet → fail closed.
    raise UnauthenticatedError(
        f"auth_mode {settings.auth_mode!r} is not available yet; only 'dev' is implemented"
    )
