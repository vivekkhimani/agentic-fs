"""The reconciler — heal catalog drift from S3 (in-memory stores)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from afs_core import keys
from afs_core.models import NamespaceRecord, TenantRecord
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.reconcile import reconcile

NOW = datetime(2026, 6, 14, tzinfo=UTC)
OLD = NOW - timedelta(hours=1)  # past the grace window


class _Collector:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def __call__(self, key: str) -> None:
        self.keys.append(key)


def _stores() -> tuple[InMemoryCatalogStore, InMemoryObjectStore]:
    return InMemoryCatalogStore(), InMemoryObjectStore()


async def _put(
    objects: InMemoryObjectStore, t: str, ns: str, path: str, body: bytes = b"hi"
) -> str:
    stat = await objects.put(keys.originals_key(t, ns, path), body, content_type="text/plain")
    return stat.etag


async def test_in_sync_is_noop() -> None:
    cat, obj = _stores()
    etag = await _put(obj, "dev", "ns", "a.txt")
    await cat.put_entry(make_entry("dev", "ns", "a.txt", etag=etag, updated_at=OLD))
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert enq.keys == []
    assert report.in_sync == 1 and report.enqueued == 0 and report.tombstoned == 0


async def test_object_without_row_is_enqueued() -> None:
    cat, obj = _stores()
    await _put(obj, "dev", "ns", "new.txt")
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert enq.keys == [keys.originals_key("dev", "ns", "new.txt")]
    assert report.enqueued == 1


async def test_tombstoned_row_with_object_is_revived() -> None:
    # a deleted-then-re-added file: object present, row tombstoned → re-extract
    cat, obj = _stores()
    etag = await _put(obj, "dev", "ns", "z.txt")
    await cat.put_entry(make_entry("dev", "ns", "z.txt", etag=etag, deleted_at=OLD, updated_at=OLD))
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert enq.keys == [keys.originals_key("dev", "ns", "z.txt")]
    assert report.enqueued == 1


async def test_changed_object_is_enqueued() -> None:
    cat, obj = _stores()
    await _put(obj, "dev", "ns", "s.txt", body=b"new bytes")  # current etag
    await cat.put_entry(make_entry("dev", "ns", "s.txt", etag="stale-etag", updated_at=OLD))
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert enq.keys == [keys.originals_key("dev", "ns", "s.txt")]
    assert report.enqueued == 1


async def test_orphan_row_is_soft_deleted_after_grace() -> None:
    cat, obj = _stores()
    keep = await _put(obj, "dev", "ns", "keep.txt")  # keeps the namespace in the sweep
    await cat.put_entry(make_entry("dev", "ns", "keep.txt", etag=keep, updated_at=OLD))
    await cat.put_entry(make_entry("dev", "ns", "gone.txt", updated_at=OLD))  # no object
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert report.tombstoned == 1
    assert await cat.get_entry("dev", "ns", "gone.txt") is None  # tombstoned (hidden)
    assert await cat.get_entry("dev", "ns", "keep.txt") is not None  # untouched


async def test_orphan_within_grace_is_left_alone() -> None:
    cat, obj = _stores()
    keep = await _put(obj, "dev", "ns", "keep.txt")
    await cat.put_entry(make_entry("dev", "ns", "keep.txt", etag=keep, updated_at=OLD))
    await cat.put_entry(make_entry("dev", "ns", "fresh.txt", updated_at=NOW))  # just written
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert report.tombstoned == 0
    assert await cat.get_entry("dev", "ns", "fresh.txt") is not None


async def test_pure_orphan_namespace_found_via_catalog() -> None:
    # a namespace whose objects are all gone (no S3 prefix) is still swept.
    cat, obj = _stores()
    await cat.put_tenant(TenantRecord(tenant_id="dev", created_at=OLD, updated_at=OLD))
    await cat.put_namespace(
        NamespaceRecord(tenant_id="dev", name="empty", created_at=OLD, updated_at=OLD)
    )
    await cat.put_entry(make_entry("dev", "empty", "orphan.txt", updated_at=OLD))
    enq = _Collector()

    report = await reconcile(cat, obj, enq, now=NOW)

    assert report.tombstoned == 1
    assert await cat.get_entry("dev", "empty", "orphan.txt") is None


async def test_idempotent_second_run_is_clean() -> None:
    cat, obj = _stores()
    etag = await _put(obj, "dev", "ns", "a.txt")
    await cat.put_entry(make_entry("dev", "ns", "a.txt", etag=etag, updated_at=OLD))

    await reconcile(cat, obj, _Collector(), now=NOW)
    enq = _Collector()
    report = await reconcile(cat, obj, enq, now=NOW)  # second pass

    assert enq.keys == [] and report.tombstoned == 0 and report.in_sync == 1
