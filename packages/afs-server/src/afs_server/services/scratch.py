"""The scratch service — a per-principal read/write workspace (plan §6, ADR 0012).

``scratch/<tenant>/<principal>/…`` is the agent's place to stash intermediate
work. Writes are gated by the principal's **atomic** scratch quota
(`adjust_scratch_usage`, which raises `QuotaExceededError`). Scratch is excluded
from the catalog/index and reconciler (`keys.is_indexable`), so it never shows up
in `fs_list`/`grep` — it's working space, not corpus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from afs_core import keys
from afs_core.errors import DocumentNotFoundError
from afs_server.schemas import ScratchListResult, ScratchReadResult, ScratchWriteResult

if TYPE_CHECKING:
    from afs_core.contracts import CatalogStore, ObjectStore
    from afs_server.auth import TenantContext

MAX_SCRATCH_LIST = 1000


class ScratchService:
    def __init__(self, catalog: CatalogStore, objects: ObjectStore) -> None:
        self._catalog = catalog
        self._objects = objects

    def _authorize(self, ctx: TenantContext) -> None:
        ctx.require_scope("fs:write:scratch")

    def _key(self, ctx: TenantContext, path: str) -> str:
        keys.validate_relpath(path)
        return keys.scratch_key(ctx.tenant_id, ctx.principal_id, path)

    async def write(self, ctx: TenantContext, path: str, content: str) -> ScratchWriteResult:
        self._authorize(ctx)
        key = self._key(ctx, path)
        body = content.encode("utf-8")

        existing = await self._objects.stat(key)
        delta_bytes = len(body) - (existing.size if existing else 0)
        delta_objects = 0 if existing else 1

        # Quota is enforced atomically *before* the write; over-quota raises.
        usage = await self._catalog.adjust_scratch_usage(
            ctx.tenant_id, ctx.principal_id, delta_bytes=delta_bytes, delta_objects=delta_objects
        )
        await self._objects.put(key, body, content_type="text/plain; charset=utf-8")
        return ScratchWriteResult(
            path=path,
            bytes=len(body),
            bytes_used=usage.bytes_used,
            objects_used=usage.objects_used,
        )

    async def read(self, ctx: TenantContext, path: str) -> ScratchReadResult:
        self._authorize(ctx)
        key = self._key(ctx, path)
        if await self._objects.stat(key) is None:
            raise DocumentNotFoundError("scratch object not found", detail={"path": path})
        raw = await self._objects.get(key)
        return ScratchReadResult(path=path, content=raw.decode("utf-8"))

    async def list(self, ctx: TenantContext, prefix: str = "") -> ScratchListResult:
        self._authorize(ctx)
        base = f"scratch/{ctx.tenant_id}/{ctx.principal_id}/"
        full_prefix = base + prefix
        paths: list[str] = []
        cursor: str | None = None
        while len(paths) < MAX_SCRATCH_LIST:
            page = await self._objects.list(full_prefix, cursor=cursor)
            paths.extend(stat.key.removeprefix(base) for stat in page.items)
            cursor = page.next_cursor
            if not cursor:
                break
        return ScratchListResult(paths=paths[:MAX_SCRATCH_LIST])

    async def delete(self, ctx: TenantContext, path: str) -> ScratchWriteResult:
        self._authorize(ctx)
        key = self._key(ctx, path)
        existing = await self._objects.stat(key)
        if existing is None:
            raise DocumentNotFoundError("scratch object not found", detail={"path": path})
        await self._objects.delete(key)
        usage = await self._catalog.adjust_scratch_usage(
            ctx.tenant_id, ctx.principal_id, delta_bytes=-existing.size, delta_objects=-1
        )
        return ScratchWriteResult(
            path=path, bytes=0, bytes_used=usage.bytes_used, objects_used=usage.objects_used
        )
