"""Shared FastAPI dependencies (typed aliases keep the routers thin)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from afs_core.errors import UnauthenticatedError
from afs_server.auth import (
    TenantContext,
    context_from_claims,
    resolve_dev_context,
)
from afs_server.services import FsService, IngestService
from afs_server.settings import Settings, load_settings

if TYPE_CHECKING:
    from afs_core.contracts import CatalogStore, ObjectStore


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def get_catalog(request: Request) -> CatalogStore:
    return request.app.state.catalog


def get_objects(request: Request) -> ObjectStore:
    return request.app.state.objects


def get_fs_service(request: Request) -> FsService:
    return FsService(request.app.state.catalog, request.app.state.objects)


def get_ingest_service(request: Request) -> IngestService:
    return IngestService(
        request.app.state.catalog,
        request.app.state.objects,
        request.app.state.extraction_pipeline,
        extraction_mode=request.app.state.settings.extraction_mode,
    )


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def get_principal(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> TenantContext:
    """The calling principal. Dev → static principal; oidc → verify the bearer
    token (shared verifier on app.state) and map its claims (ADR 0013)."""
    if settings.auth_mode == "dev":
        return resolve_dev_context(settings)
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise UnauthenticatedError("oidc auth is not configured")
    token = _bearer_token(request)
    access = await verifier.verify_token(token) if token else None
    if access is None:
        raise UnauthenticatedError("missing or invalid bearer token")
    return context_from_claims(access.claims, settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]
CatalogDep = Annotated["CatalogStore", Depends(get_catalog)]
FsDep = Annotated[FsService, Depends(get_fs_service)]
IngestDep = Annotated[IngestService, Depends(get_ingest_service)]
PrincipalDep = Annotated[TenantContext, Depends(get_principal)]
