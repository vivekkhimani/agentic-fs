"""Conformance kits — abstract pytest classes a backend subclasses to certify.

Subclass the kit, override the ``store`` fixture to point at your impl, and make
it green. The base classes are intentionally *not* named ``Test*`` so pytest does
not collect them directly (their abstract fixture would error); only your
``Test...`` subclass is collected.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from afs_core.contracts import CatalogStore, Connector, Normalizer, ObjectStore
from afs_core.errors import NotFoundError, QuotaExceededError
from afs_core.models import (
    CatalogEntry,
    ExtractionState,
    NamespaceRecord,
    PrincipalRecord,
    SourceDocument,
    SourceItem,
    SyncCheckpoint,
    TenantRecord,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_entry(tenant_id: str, namespace: str, path: str, **over: object) -> CatalogEntry:
    """Build a CatalogEntry with sensible defaults for tests."""
    base: dict[str, object] = {
        "tenant_id": tenant_id,
        "namespace": namespace,
        "path": path,
        "entry_id": f"ID-{tenant_id}-{namespace}-{path}".replace("/", "_"),
        "size": 1,
        "etag": "e",
        "checksum": "sha-default",
        "content_type": "text/plain",
        "title": path,
        "extraction": ExtractionState(status="pending"),
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    base.update(over)
    return CatalogEntry(**base)  # type: ignore[arg-type]


class ObjectStoreConformance:
    """Certifies an ``ObjectStore`` implementation."""

    @pytest.fixture
    def store(self) -> ObjectStore:
        raise NotImplementedError("override `store` to point at your impl")

    async def test_put_get_roundtrip(self, store: ObjectStore) -> None:
        stat = await store.put("tenants/a/ns/x.txt", b"hello", content_type="text/plain")
        assert stat.size == 5
        assert await store.get("tenants/a/ns/x.txt") == b"hello"

    async def test_ranged_get_is_inclusive(self, store: ObjectStore) -> None:
        await store.put("k", b"0123456789")
        assert await store.get("k", start=2, end=4) == b"234"
        assert await store.get("k", start=7) == b"789"

    async def test_stat_missing_is_none(self, store: ObjectStore) -> None:
        assert await store.stat("nope") is None

    async def test_get_missing_raises_not_found(self, store: ObjectStore) -> None:
        with pytest.raises(NotFoundError):
            await store.get("nope")

    async def test_list_prefix_and_stable_pagination(self, store: ObjectStore) -> None:
        for i in range(5):
            await store.put(f"p/{i}", b"x")
        await store.put("other/z", b"x")
        first = await store.list("p/", limit=2)
        assert [o.key for o in first.items] == ["p/0", "p/1"]
        assert first.next_cursor is not None
        second = await store.list("p/", cursor=first.next_cursor, limit=2)
        assert [o.key for o in second.items] == ["p/2", "p/3"]

    async def test_delete_and_delete_prefix(self, store: ObjectStore) -> None:
        await store.put("d/1", b"x")
        await store.put("d/2", b"x")
        await store.delete("d/1")
        assert await store.stat("d/1") is None
        removed = await store.delete_prefix("d/")
        assert removed == 1
        assert (await store.list("d/")).items == []

    async def test_presign_shapes(self, store: ObjectStore) -> None:
        put = await store.presigned_put("k", content_type="text/plain", max_bytes=100)
        assert put.url and put.max_bytes == 100
        assert isinstance(await store.presigned_get("k"), str)


class CatalogStoreConformance:
    """Certifies a ``CatalogStore`` implementation."""

    @pytest.fixture
    def store(self) -> CatalogStore:
        raise NotImplementedError("override `store` to point at your impl")

    async def test_put_get_entry(self, store: CatalogStore) -> None:
        await store.put_entry(make_entry("a", "ns", "x.txt"))
        got = await store.get_entry("a", "ns", "x.txt")
        assert got is not None and got.path == "x.txt"

    async def test_tenant_isolation(self, store: CatalogStore) -> None:
        await store.put_entry(make_entry("a", "ns", "secret.txt"))
        assert await store.get_entry("b", "ns", "secret.txt") is None
        assert (await store.list_entries("b", "ns")).items == []

    async def test_list_prefix_and_pagination(self, store: CatalogStore) -> None:
        for i in range(4):
            await store.put_entry(make_entry("a", "ns", f"docs/{i}.txt"))
        await store.put_entry(make_entry("a", "ns", "other.txt"))
        page = await store.list_entries("a", "ns", prefix="docs/", limit=2)
        assert [e.path for e in page.items] == ["docs/0.txt", "docs/1.txt"]
        assert page.next_cursor is not None
        rest = await store.list_entries("a", "ns", prefix="docs/", cursor=page.next_cursor, limit=2)
        assert [e.path for e in rest.items] == ["docs/2.txt", "docs/3.txt"]

    async def test_tombstone_then_hard_delete(self, store: CatalogStore) -> None:
        await store.put_entry(make_entry("a", "ns", "x.txt"))
        await store.delete_entry("a", "ns", "x.txt")  # soft
        assert await store.get_entry("a", "ns", "x.txt") is None
        with_deleted = await store.list_entries("a", "ns", include_deleted=True)
        assert any(e.path == "x.txt" and e.deleted_at is not None for e in with_deleted.items)
        await store.delete_entry("a", "ns", "x.txt", hard=True)
        gone = await store.list_entries("a", "ns", include_deleted=True)
        assert all(e.path != "x.txt" for e in gone.items)

    async def test_extraction_state_and_status_index(self, store: CatalogStore) -> None:
        await store.put_entry(make_entry("a", "ns", "x.txt"))
        await store.set_extraction(
            "a", "ns", "x.txt", ExtractionState(status="catalog_only", reason="encrypted")
        )
        got = await store.get_entry("a", "ns", "x.txt")
        assert got is not None and got.extraction.status == "catalog_only"
        page = await store.list_by_extraction_status("catalog_only")
        assert any(e.path == "x.txt" for e in page.items)

    async def test_set_extraction_missing_raises(self, store: CatalogStore) -> None:
        with pytest.raises(NotFoundError):
            await store.set_extraction("a", "ns", "missing", ExtractionState(status="pending"))

    async def test_tree_version_bumps_on_write(self, store: CatalogStore) -> None:
        before = await store.tree_version("a", "ns")
        await store.put_entry(make_entry("a", "ns", "x.txt"))
        after = await store.tree_version("a", "ns")
        assert before != after

    async def test_find_by_checksum(self, store: CatalogStore) -> None:
        await store.put_entry(make_entry("a", "ns", "x.txt", checksum="sha-xyz"))
        await store.put_entry(make_entry("a", "ns2", "y.txt", checksum="sha-xyz"))
        hits = await store.find_by_checksum("a", "sha-xyz")
        assert {e.path for e in hits} == {"x.txt", "y.txt"}

    async def test_control_records_roundtrip(self, store: CatalogStore) -> None:
        await store.put_tenant(TenantRecord(tenant_id="a", created_at=_NOW, updated_at=_NOW))
        assert (await store.get_tenant("a")) is not None
        await store.put_namespace(
            NamespaceRecord(tenant_id="a", name="ns", created_at=_NOW, updated_at=_NOW)
        )
        assert [n.name for n in await store.list_namespaces("a")] == ["ns"]
        await store.delete_namespace("a", "ns")
        assert await store.get_namespace("a", "ns") is None

    async def test_checkpoint_roundtrip(self, store: CatalogStore) -> None:
        assert await store.get_checkpoint("a", "conn") is None
        await store.put_checkpoint("a", "conn", SyncCheckpoint(connector_id="conn", cursor="c1"))
        cp = await store.get_checkpoint("a", "conn")
        assert cp is not None and cp.cursor == "c1"

    async def test_scratch_quota_enforced_and_atomic(self, store: CatalogStore) -> None:
        await store.put_principal(
            PrincipalRecord(
                tenant_id="a",
                principal_id="p",
                scratch_quota_bytes=100,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        usage = await store.adjust_scratch_usage("a", "p", delta_bytes=60, delta_objects=1)
        assert usage.bytes_used == 60
        with pytest.raises(QuotaExceededError):
            await store.adjust_scratch_usage("a", "p", delta_bytes=60, delta_objects=1)
        # Atomic: the rejected adjustment left usage unchanged.
        assert (await store.get_scratch_usage("a", "p")).bytes_used == 60


class NormalizerConformance:
    """Certifies a ``Normalizer`` implementation.

    Override two fixtures: ``normalizer`` (your impl) and ``sample`` (a
    ``SourceDocument`` it accepts, pointing at a real file on disk).
    """

    @pytest.fixture
    def normalizer(self) -> Normalizer:
        raise NotImplementedError("override `normalizer` to point at your impl")

    @pytest.fixture
    def sample(self) -> SourceDocument:
        raise NotImplementedError("override `sample` with a doc your normalizer accepts")

    def test_accepts_its_sample(self, normalizer: Normalizer, sample: SourceDocument) -> None:
        assert normalizer.accepts(sample) is True

    async def test_normalize_produces_pages(
        self, normalizer: Normalizer, sample: SourceDocument
    ) -> None:
        result = await normalizer.normalize(sample)
        assert result.pages, "a successful normalize must yield at least one page"
        assert all(p.number >= 1 for p in result.pages)
        assert result.quality.page_count == len(result.pages)


class ConnectorConformance:
    """Certifies a ``Connector`` implementation.

    Override ``connector`` to return your impl pointed at a source already
    populated with at least two documents.
    """

    @pytest.fixture
    def connector(self) -> Connector:
        raise NotImplementedError("override `connector` with an impl over a populated source")

    def test_discovers_clean_relative_paths(self, connector: Connector) -> None:
        items = list(connector.discover())
        assert items, "discover() must yield the source's documents"
        for item in items:
            assert isinstance(item, SourceItem)
            assert item.path and not item.path.startswith("/"), "paths are relative POSIX paths"
            assert ".." not in item.path.split("/"), "no parent-traversal segments"
            assert item.locator, "every item needs a locator fetch() can use"

    def test_discover_is_repeatable(self, connector: Connector) -> None:
        # The engine may enumerate more than once (e.g. with --prune); discovery
        # must not be a one-shot generator that exhausts.
        first = {item.path for item in connector.discover()}
        second = {item.path for item in connector.discover()}
        assert first == second

    def test_fetch_returns_bytes(self, connector: Connector) -> None:
        item = next(iter(connector.discover()))
        assert isinstance(connector.fetch(item), bytes)
