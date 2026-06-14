"""The scratch workspace service — write/read/list/delete + atomic quota."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from afs_core.errors import (
    DocumentNotFoundError,
    InsufficientScopeError,
    QuotaExceededError,
)
from afs_core.models import PrincipalRecord
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore
from afs_server.auth import TenantContext
from afs_server.services import ScratchService

CTX = TenantContext(
    tenant_id="dev", principal_id="p", scopes=frozenset({"fs:write:scratch"}), namespaces=None
)


async def _svc(quota: int | None = None) -> ScratchService:
    cat, obj = InMemoryCatalogStore(), InMemoryObjectStore()
    if quota is not None:
        now = datetime(2026, 6, 14, tzinfo=UTC)
        await cat.put_principal(
            PrincipalRecord(
                tenant_id="dev",
                principal_id="p",
                scratch_quota_bytes=quota,
                created_at=now,
                updated_at=now,
            )
        )
    return ScratchService(cat, obj)


async def test_write_read_roundtrip() -> None:
    svc = await _svc()
    res = await svc.write(CTX, "notes/a.md", "hello scratch")
    assert res.bytes == len(b"hello scratch") and res.objects_used == 1
    got = await svc.read(CTX, "notes/a.md")
    assert got.content == "hello scratch"


async def test_list_scoped_and_delete() -> None:
    svc = await _svc()
    await svc.write(CTX, "a.txt", "x")
    await svc.write(CTX, "sub/b.txt", "y")
    assert set((await svc.list(CTX)).paths) == {"a.txt", "sub/b.txt"}
    assert (await svc.list(CTX, "sub/")).paths == ["sub/b.txt"]
    res = await svc.delete(CTX, "a.txt")
    assert res.objects_used == 1  # only sub/b.txt remains
    assert (await svc.list(CTX)).paths == ["sub/b.txt"]


async def test_read_missing_is_not_found() -> None:
    svc = await _svc()
    with pytest.raises(DocumentNotFoundError):
        await svc.read(CTX, "nope.txt")


async def test_quota_enforced() -> None:
    svc = await _svc(quota=10)
    await svc.write(CTX, "a", "12345")  # 5 bytes — ok
    with pytest.raises(QuotaExceededError):
        await svc.write(CTX, "b", "1234567890")  # +10 → 15 > 10


async def test_overwrite_adjusts_by_delta() -> None:
    svc = await _svc(quota=10)
    await svc.write(CTX, "a", "12345")  # 5 bytes used
    res = await svc.write(CTX, "a", "67")  # overwrite → 2 bytes (delta -3)
    assert res.bytes_used == 2 and res.objects_used == 1


async def test_requires_scratch_scope() -> None:
    svc = await _svc()
    no_scope = TenantContext(tenant_id="dev", principal_id="p", scopes=frozenset(), namespaces=None)
    with pytest.raises(InsufficientScopeError):
        await svc.write(no_scope, "a", "x")
