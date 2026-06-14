"""The sync engine's decisions: ingest, checksum-skip, L1 version-skip, prune,
incremental (delta + checkpoint), dry-run, and per-doc error isolation."""

from __future__ import annotations

import hashlib

from afs_connector_sdk.engine import SyncEngine
from afs_core.models import ChangeSet, SourceItem


class _FakeClient:
    """Stands in for IngestClient. `existing` maps path -> a stat entry dict
    (``{"checksum": ..., "source": {"version": ...}}``)."""

    def __init__(self, existing: dict[str, dict] | None = None) -> None:
        self.existing = existing or {}
        self.put: list[tuple[str, str | None]] = []  # (path, source_version)
        self.deleted: list[str] = []
        self.checkpoints: dict[str, str] = {}

    async def stat(self, namespace: str, path: str) -> dict | None:
        return self.existing.get(path)

    async def put_document(
        self,
        namespace: str,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        connector_id: str | None = None,
        remote_id: str | None = None,
        source_version: str | None = None,
    ) -> dict:
        self.put.append((path, source_version))
        return {}

    async def list_paths(self, namespace: str, prefix: str = "") -> list[str]:
        return list(self.existing)

    async def delete_document(self, namespace: str, path: str) -> None:
        self.deleted.append(path)

    async def get_checkpoint(self, connector_id: str) -> str | None:
        return self.checkpoints.get(connector_id)

    async def put_checkpoint(self, connector_id: str, cursor: str) -> None:
        self.checkpoints[connector_id] = cursor


class _FakeConnector:
    name = "fake"

    def __init__(
        self,
        items: dict[str, bytes],
        *,
        versions: dict[str, str] | None = None,
        broken: set[str] | None = None,
    ) -> None:
        self._items = items
        self._versions = versions or {}
        self._broken = broken or set()
        self.fetched: list[str] = []

    def discover(self) -> list[SourceItem]:
        return [SourceItem(path=p, locator=p, version=self._versions.get(p)) for p in self._items]

    def fetch(self, item: SourceItem) -> bytes:
        if item.locator in self._broken:
            raise OSError("unreadable")
        self.fetched.append(item.locator)
        return self._items[item.locator]


class _FakeIncrementalConnector:
    name = "inc"

    def __init__(self, changes: ChangeSet) -> None:
        self._changes = changes
        self.seen_cursor: str | None | object = "UNSET"
        self.fetched: list[str] = []

    def discover(self) -> list[SourceItem]:
        return []

    def fetch(self, item: SourceItem) -> bytes:
        self.fetched.append(item.locator)
        return b"data:" + item.locator.encode()

    def discover_changes(self, cursor: str | None) -> ChangeSet:
        self.seen_cursor = cursor
        return self._changes


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(checksum: str, version: str | None = None) -> dict:
    e: dict = {"checksum": checksum}
    if version is not None:
        e["source"] = {"version": version}
    return e


async def test_ingests_new_documents() -> None:
    client = _FakeClient()
    connector = _FakeConnector({"a.md": b"alpha", "sub/b.txt": b"beta"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.ingested == 2 and report.skipped == 0
    assert {p for p, _ in client.put} == {"a.md", "sub/b.txt"}


async def test_skips_unchanged_by_checksum() -> None:
    client = _FakeClient(existing={"a.md": _entry(_sha(b"alpha"))})
    connector = _FakeConnector({"a.md": b"alpha", "b.md": b"new"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.skipped == 1 and report.ingested == 1
    assert [p for p, _ in client.put] == ["b.md"]


async def test_l1_version_match_skips_the_fetch() -> None:
    client = _FakeClient(existing={"a.md": _entry("stale-checksum", version="v1")})
    connector = _FakeConnector({"a.md": b"alpha"}, versions={"a.md": "v1"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.skipped == 1 and report.ingested == 0
    assert connector.fetched == []  # the whole point: no download


async def test_l1_changed_version_refetches_and_ingests() -> None:
    client = _FakeClient(existing={"a.md": _entry(_sha(b"old"), version="v1")})
    connector = _FakeConnector({"a.md": b"alpha"}, versions={"a.md": "v2"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.ingested == 1
    assert connector.fetched == ["a.md"]
    assert client.put == [("a.md", "v2")]  # the new version is stamped


async def test_dry_run_writes_nothing() -> None:
    client = _FakeClient()
    connector = _FakeConnector({"a.md": b"alpha"})
    report = await SyncEngine(client, dry_run=True).sync(connector, "ns")
    assert report.ingested == 1
    assert client.put == []


async def test_prune_deletes_documents_absent_from_source() -> None:
    client = _FakeClient(existing={"gone.md": _entry(_sha(b"old"))})
    connector = _FakeConnector({"a.md": b"alpha"})
    report = await SyncEngine(client, prune=True).sync(connector, "ns")
    assert report.ingested == 1 and report.deleted == 1
    assert client.deleted == ["gone.md"]


async def test_one_bad_document_does_not_abort_the_crawl() -> None:
    client = _FakeClient()
    connector = _FakeConnector({"good.md": b"ok", "bad.md": b"x"}, broken={"bad.md"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.ingested == 1 and report.failed == 1
    assert [p for p, _ in client.put] == ["good.md"]
    assert any("bad.md" in e for e in report.errors)


async def test_incremental_processes_changes_and_persists_cursor() -> None:
    client = _FakeClient()
    client.checkpoints["inc"] = "c1"
    changes = ChangeSet(
        items=[SourceItem(path="new.md", locator="id-new", version="r9")],
        deleted=["old.md"],
        cursor="c2",
    )
    connector = _FakeIncrementalConnector(changes)
    report = await SyncEngine(client).sync(connector, "ns")
    assert connector.seen_cursor == "c1"  # resumed from the stored cursor
    assert report.ingested == 1 and report.deleted == 1
    assert client.deleted == ["old.md"]
    assert client.checkpoints["inc"] == "c2"  # new cursor persisted


async def test_incremental_first_run_passes_none_cursor() -> None:
    client = _FakeClient()  # no checkpoint yet
    connector = _FakeIncrementalConnector(
        ChangeSet(items=[SourceItem(path="a.md", locator="id-a")], cursor="start")
    )
    await SyncEngine(client).sync(connector, "ns")
    assert connector.seen_cursor is None
    assert client.checkpoints["inc"] == "start"
