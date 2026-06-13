"""Shared FastAPI dependencies (typed aliases keep the routers thin)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from afs_server.auth import TenantContext, resolve_context
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
    )


def get_principal(settings: Annotated[Settings, Depends(get_settings)]) -> TenantContext:
    return resolve_context(settings)


SettingsDep = Annotated[Settings, Depends(get_settings)]
CatalogDep = Annotated["CatalogStore", Depends(get_catalog)]
FsDep = Annotated[FsService, Depends(get_fs_service)]
IngestDep = Annotated[IngestService, Depends(get_ingest_service)]
PrincipalDep = Annotated[TenantContext, Depends(get_principal)]
