"""In-memory fakes for the contracts — the reference impls tests run against.

These are not production stores; they exist so unit tests run with zero
infrastructure and so the conformance kits have something to certify out of the
box. Every real backend must make the same conformance kit green.
"""

from __future__ import annotations

import base64
import hashlib
from bisect import bisect_right
from datetime import UTC, datetime, timedelta

from afs_core.errors import NotFoundError, QuotaExceededError
from afs_core.models import (
    CatalogEntry,
    ExtractionState,
    NamespaceRecord,
    ObjectStat,
    Page,
    PresignedPut,
    PrincipalRecord,
    ScratchUsage,
    SyncCheckpoint,
    TenantRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def _decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


def _paginate[K](
    sorted_keys: list[K], cursor: str | None, limit: int
) -> tuple[list[K], str | None]:
    """Stable opaque-cursor pagination over a sorted key list."""
    start = 0
    if cursor is not None:
        after = _decode_cursor(cursor)
        start = bisect_right([str(k) for k in sorted_keys], after)
    window = sorted_keys[start : start + limit]
    has_more = start + limit < len(sorted_keys)
    next_cursor = _encode_cursor(str(window[-1])) if has_more and window else None
    return window, next_cursor


class InMemoryObjectStore:
    """In-memory ``ObjectStore``."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, ObjectStat]] = {}

    async def get(self, key: str, *, start: int | None = None, end: int | None = None) -> bytes:
        if key not in self._data:
            raise NotFoundError("object not found", detail={"key": key})
        body = self._data[key][0]
        if start is None and end is None:
            return body
        lo = start or 0
        hi = (end + 1) if end is not None else len(body)
        return body[lo:hi]

    async def put(self, key: str, body: bytes, *, content_type: str | None = None) -> ObjectStat:
        stat = ObjectStat(
            key=key,
            size=len(body),
            etag=hashlib.md5(body).hexdigest(),
            content_type=content_type,
            last_modified=_now(),
        )
        self._data[key] = (body, stat)
        return stat

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def delete_prefix(self, prefix: str) -> int:
        keys = [k for k in self._data if k.startswith(prefix)]
        for k in keys:
            del self._data[k]
        return len(keys)

    async def stat(self, key: str) -> ObjectStat | None:
        found = self._data.get(key)
        return found[1] if found else None

    async def list(
        self, prefix: str, *, cursor: str | None = None, limit: int = 1000
    ) -> Page[ObjectStat]:
        keys = sorted(k for k in self._data if k.startswith(prefix))
        window, next_cursor = _paginate(keys, cursor, limit)
        return Page(items=[self._data[k][1] for k in window], next_cursor=next_cursor)

    async def presigned_put(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int = 900
    ) -> PresignedPut:
        return PresignedPut(
            url=f"memory://put/{key}",
            headers={"Content-Type": content_type},
            expires_at=_now() + timedelta(seconds=expires_in),
            max_bytes=max_bytes,
        )

    async def presigned_get(self, key: str, *, expires_in: int = 300) -> str:
        return f"memory://get/{key}"


class InMemoryCatalogStore:
    """In-memory ``CatalogStore`` covering entries, control records, checkpoints, quota."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], CatalogEntry] = {}
        self._tenants: dict[str, TenantRecord] = {}
        self._namespaces: dict[tuple[str, str], NamespaceRecord] = {}
        self._principals: dict[tuple[str, str], PrincipalRecord] = {}
        self._checkpoints: dict[tuple[str, str], SyncCheckpoint] = {}
        self._scratch: dict[tuple[str, str], ScratchUsage] = {}
        self._tree_versions: dict[tuple[str, str], int] = {}

    def _bump_tree(self, tenant_id: str, namespace: str) -> None:
        key = (tenant_id, namespace)
        self._tree_versions[key] = self._tree_versions.get(key, 0) + 1

    # -- entries --
    async def put_entry(self, entry: CatalogEntry) -> None:
        self._entries[(entry.tenant_id, entry.namespace, entry.path)] = entry
        self._bump_tree(entry.tenant_id, entry.namespace)

    async def get_entry(self, tenant_id: str, namespace: str, path: str) -> CatalogEntry | None:
        entry = self._entries.get((tenant_id, namespace, path))
        if entry is None or entry.deleted_at is not None:
            return None
        return entry

    async def delete_entry(
        self, tenant_id: str, namespace: str, path: str, *, hard: bool = False
    ) -> None:
        key = (tenant_id, namespace, path)
        entry = self._entries.get(key)
        if entry is None:
            return
        if hard:
            del self._entries[key]
        else:
            self._entries[key] = entry.model_copy(update={"deleted_at": _now()})
        self._bump_tree(tenant_id, namespace)

    async def list_entries(
        self,
        tenant_id: str,
        namespace: str,
        *,
        prefix: str = "",
        include_deleted: bool = False,
        cursor: str | None = None,
        limit: int = 1000,
    ) -> Page[CatalogEntry]:
        paths = sorted(
            path
            for (t, ns, path), e in self._entries.items()
            if t == tenant_id
            and ns == namespace
            and path.startswith(prefix)
            and (include_deleted or e.deleted_at is None)
        )
        window, next_cursor = _paginate(paths, cursor, limit)
        items = [self._entries[(tenant_id, namespace, p)] for p in window]
        return Page(items=items, next_cursor=next_cursor)

    async def find_by_checksum(self, tenant_id: str, checksum: str) -> list[CatalogEntry]:
        return [
            e
            for (t, _, _), e in self._entries.items()
            if t == tenant_id and e.checksum == checksum and e.deleted_at is None
        ]

    async def set_extraction(
        self, tenant_id: str, namespace: str, path: str, state: ExtractionState
    ) -> None:
        key = (tenant_id, namespace, path)
        entry = self._entries.get(key)
        if entry is None:
            raise NotFoundError("entry not found", detail={"path": path})
        self._entries[key] = entry.model_copy(update={"extraction": state, "updated_at": _now()})
        self._bump_tree(tenant_id, namespace)

    async def list_by_extraction_status(
        self, status: str, *, cursor: str | None = None, limit: int = 100
    ) -> Page[CatalogEntry]:
        matches = sorted(
            (
                e
                for e in self._entries.values()
                if e.extraction.status == status and e.deleted_at is None
            ),
            key=lambda e: e.entry_id,
        )
        ids = [e.entry_id for e in matches]
        window, next_cursor = _paginate(ids, cursor, limit)
        by_id = {e.entry_id: e for e in matches}
        return Page(items=[by_id[i] for i in window], next_cursor=next_cursor)

    async def tree_version(self, tenant_id: str, namespace: str) -> str:
        return str(self._tree_versions.get((tenant_id, namespace), 0))

    # -- control records --
    async def put_tenant(self, tenant: TenantRecord) -> None:
        self._tenants[tenant.tenant_id] = tenant

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self._tenants.get(tenant_id)

    async def list_tenants(
        self, *, cursor: str | None = None, limit: int = 100
    ) -> Page[TenantRecord]:
        ids = sorted(self._tenants)
        window, next_cursor = _paginate(ids, cursor, limit)
        return Page(items=[self._tenants[i] for i in window], next_cursor=next_cursor)

    async def put_namespace(self, ns: NamespaceRecord) -> None:
        self._namespaces[(ns.tenant_id, ns.name)] = ns

    async def get_namespace(self, tenant_id: str, name: str) -> NamespaceRecord | None:
        return self._namespaces.get((tenant_id, name))

    async def list_namespaces(self, tenant_id: str) -> list[NamespaceRecord]:
        return [ns for (t, _), ns in self._namespaces.items() if t == tenant_id]

    async def delete_namespace(self, tenant_id: str, name: str) -> None:
        self._namespaces.pop((tenant_id, name), None)

    async def put_principal(self, p: PrincipalRecord) -> None:
        self._principals[(p.tenant_id, p.principal_id)] = p

    async def get_principal(self, tenant_id: str, principal_id: str) -> PrincipalRecord | None:
        return self._principals.get((tenant_id, principal_id))

    async def list_principals(self, tenant_id: str) -> list[PrincipalRecord]:
        return [p for (t, _), p in self._principals.items() if t == tenant_id]

    # -- checkpoints --
    async def get_checkpoint(self, tenant_id: str, connector_id: str) -> SyncCheckpoint | None:
        return self._checkpoints.get((tenant_id, connector_id))

    async def put_checkpoint(self, tenant_id: str, connector_id: str, cp: SyncCheckpoint) -> None:
        self._checkpoints[(tenant_id, connector_id)] = cp

    # -- scratch quota (atomic) --
    async def get_scratch_usage(self, tenant_id: str, principal_id: str) -> ScratchUsage:
        existing = self._scratch.get((tenant_id, principal_id))
        if existing is not None:
            return existing
        return ScratchUsage(tenant_id=tenant_id, principal_id=principal_id)

    async def adjust_scratch_usage(
        self, tenant_id: str, principal_id: str, *, delta_bytes: int, delta_objects: int
    ) -> ScratchUsage:
        current = await self.get_scratch_usage(tenant_id, principal_id)
        principal = self._principals.get((tenant_id, principal_id))
        quota = principal.scratch_quota_bytes if principal else None

        new_bytes = current.bytes_used + delta_bytes
        if quota is not None and new_bytes > quota:
            raise QuotaExceededError(
                "scratch quota exceeded",
                detail={"quota_bytes": quota, "attempted_bytes": new_bytes},
            )
        updated = ScratchUsage(
            tenant_id=tenant_id,
            principal_id=principal_id,
            bytes_used=max(0, new_bytes),
            objects_used=max(0, current.objects_used + delta_objects),
            quota_bytes=quota,
        )
        self._scratch[(tenant_id, principal_id)] = updated
        return updated
