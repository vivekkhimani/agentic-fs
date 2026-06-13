"""Read-path data plane: list / stat / ranged read. Scope: fs:read."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from afs_core.models import CatalogEntry
from afs_server.dependencies import FsDep, PrincipalDep
from afs_server.schemas import EntryPage, ReadResponse

router = APIRouter(prefix="/v1/fs", tags=["fs"])


@router.get("/{namespace}/entries", response_model=EntryPage)
async def list_entries(
    namespace: str,
    fs: FsDep,
    principal: PrincipalDep,
    prefix: Annotated[str, Query()] = "",
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> EntryPage:
    return await fs.list_entries(principal, namespace, prefix=prefix, cursor=cursor, limit=limit)


@router.get("/{namespace}/stat", response_model=CatalogEntry)
async def stat(
    namespace: str,
    fs: FsDep,
    principal: PrincipalDep,
    path: Annotated[str, Query()],
) -> CatalogEntry:
    return await fs.stat(principal, namespace, path)


@router.get("/{namespace}/doc", response_model=ReadResponse)
async def read_doc(
    namespace: str,
    fs: FsDep,
    principal: PrincipalDep,
    path: Annotated[str, Query()],
    start_page: Annotated[int, Query(ge=1)] = 1,
    end_page: Annotated[int | None, Query(ge=1)] = None,
) -> ReadResponse:
    return await fs.read(principal, namespace, path, start_page=start_page, end_page=end_page)
