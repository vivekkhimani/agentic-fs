"""The ``CatalogStore`` contract (plan §5.1).

One contract covers entries + control records + checkpoints + scratch quota, so a
self-hoster swaps **one** stateful dependency. Structural ``Protocol``, async.
Certify an impl with ``CatalogStoreConformance`` (afs_core.testing); DynamoDB and
Postgres are the two reference implementations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from afs_core.models import (
    CatalogEntry,
    ExtractionState,
    NamespaceRecord,
    Page,
    PrincipalRecord,
    ScratchUsage,
    SyncCheckpoint,
    TenantRecord,
)


@runtime_checkable
class CatalogStore(Protocol):
    # -- entries (derived index of S3; healable FROM S3) --
    async def put_entry(self, entry: CatalogEntry) -> None: ...

    async def get_entry(self, tenant_id: str, namespace: str, path: str) -> CatalogEntry | None: ...

    async def delete_entry(
        self, tenant_id: str, namespace: str, path: str, *, hard: bool = False
    ) -> None:
        """Tombstone (soft) by default; ``hard=True`` removes the row entirely."""
        ...

    async def list_entries(
        self,
        tenant_id: str,
        namespace: str,
        *,
        prefix: str = "",
        include_deleted: bool = False,
        cursor: str | None = None,
        limit: int = 1000,
    ) -> Page[CatalogEntry]: ...

    async def find_by_checksum(self, tenant_id: str, checksum: str) -> list[CatalogEntry]: ...

    async def set_extraction(
        self, tenant_id: str, namespace: str, path: str, state: ExtractionState
    ) -> None: ...

    async def list_by_extraction_status(
        self, status: str, *, cursor: str | None = None, limit: int = 100
    ) -> Page[CatalogEntry]: ...

    async def tree_version(self, tenant_id: str, namespace: str) -> str:
        """A token bumped on any write to the namespace — the tree-cache key."""
        ...

    # -- control records (tenants / namespaces / principals) --
    async def put_tenant(self, tenant: TenantRecord) -> None: ...
    async def get_tenant(self, tenant_id: str) -> TenantRecord | None: ...
    async def list_tenants(
        self, *, cursor: str | None = None, limit: int = 100
    ) -> Page[TenantRecord]: ...

    async def put_namespace(self, ns: NamespaceRecord) -> None: ...
    async def get_namespace(self, tenant_id: str, name: str) -> NamespaceRecord | None: ...
    async def list_namespaces(self, tenant_id: str) -> list[NamespaceRecord]: ...
    async def delete_namespace(self, tenant_id: str, name: str) -> None: ...

    async def put_principal(self, p: PrincipalRecord) -> None: ...
    async def get_principal(self, tenant_id: str, principal_id: str) -> PrincipalRecord | None: ...
    async def list_principals(self, tenant_id: str) -> list[PrincipalRecord]: ...

    # -- connector checkpoints --
    async def get_checkpoint(self, tenant_id: str, connector_id: str) -> SyncCheckpoint | None: ...
    async def put_checkpoint(
        self, tenant_id: str, connector_id: str, cp: SyncCheckpoint
    ) -> None: ...

    # -- scratch quota (atomic; raises QuotaExceededError) --
    async def adjust_scratch_usage(
        self, tenant_id: str, principal_id: str, *, delta_bytes: int, delta_objects: int
    ) -> ScratchUsage: ...

    async def get_scratch_usage(self, tenant_id: str, principal_id: str) -> ScratchUsage: ...
