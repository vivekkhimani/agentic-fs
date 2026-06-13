"""The read-path service: list / stat / read over the catalog + object stores.

Authority is enforced here (scope + namespace), every read is bounded, and misses
return 404 (no enumeration) — the load-bearing rules from the plan (§2.1, §6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from afs_core import keys
from afs_core.errors import (
    CatalogOnlyError,
    DocumentNotFoundError,
    NamespaceNotFoundError,
)
from afs_server.schemas import EntryPage, ReadPage, ReadResponse

if TYPE_CHECKING:
    from afs_core.contracts import CatalogStore, ObjectStore
    from afs_server.auth import TenantContext

MAX_READ_PAGES = 20


class FsService:
    def __init__(self, catalog: CatalogStore, objects: ObjectStore) -> None:
        self._catalog = catalog
        self._objects = objects

    def _authorize(self, ctx: TenantContext, namespace: str) -> None:
        ctx.require_scope("fs:read")
        if not ctx.allows_namespace(namespace):
            # 404, not 403 — a caller cannot tell "not granted" from "does not exist".
            raise NamespaceNotFoundError("namespace not found", detail={"namespace": namespace})

    async def list_entries(
        self,
        ctx: TenantContext,
        namespace: str,
        *,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 100,
    ) -> EntryPage:
        self._authorize(ctx, namespace)
        return await self._catalog.list_entries(
            ctx.tenant_id, namespace, prefix=prefix, cursor=cursor, limit=limit
        )

    async def stat(self, ctx: TenantContext, namespace: str, path: str):
        self._authorize(ctx, namespace)
        keys.validate_relpath(path)
        entry = await self._catalog.get_entry(ctx.tenant_id, namespace, path)
        if entry is None:
            raise DocumentNotFoundError("document not found", detail={"path": path})
        return entry

    async def read(
        self,
        ctx: TenantContext,
        namespace: str,
        path: str,
        *,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> ReadResponse:
        entry = await self.stat(ctx, namespace, path)

        if entry.extraction.status != "extracted":
            raise CatalogOnlyError(
                "this document exists but isn't readable yet — you can still cite it",
                detail={"path": path, "status": entry.extraction.status},
            )

        page_count = entry.extraction.page_count or 0
        start = max(1, start_page)
        end = page_count if end_page is None else min(end_page, page_count)
        if end - start + 1 > MAX_READ_PAGES:
            end = start + MAX_READ_PAGES - 1
        truncated = end < page_count or (end_page is not None and end_page > page_count)

        pages: list[ReadPage] = []
        for page in range(start, end + 1):
            key = keys.derived_text_key(ctx.tenant_id, namespace, entry.entry_id, page)
            raw = await self._objects.get(key)
            pages.append(ReadPage(page=page, text=raw.decode("utf-8")))

        return ReadResponse(
            path=path,
            pages=pages,
            page_count=page_count,
            range=(start, end if end >= start else start),
            truncated=truncated,
        )
