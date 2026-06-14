"""The sync engine's decisions: ingest new, skip unchanged, prune, dry-run, errors."""

from __future__ import annotations

import hashlib

from afs_connector_sdk.engine import SyncEngine
from afs_core.models import SourceItem


class _FakeClient:
    """Stands in for IngestClient. `existing` maps path -> stored checksum."""

    def __init__(self, existing: dict[str, str] | None = None) -> None:
        self.existing = existing or {}
        self.put: list[tuple[str, bytes]] = []
        self.deleted: list[str] = []

    async def stat(self, namespace: str, path: str) -> dict[str, str] | None:
        checksum = self.existing.get(path)
        return {"checksum": checksum} if checksum is not None else None

    async def put_document(
        self, namespace: str, path: str, data: bytes, *, content_type: str | None = None
    ) -> dict[str, str]:
        self.put.append((path, data))
        return {}

    async def list_paths(self, namespace: str, prefix: str = "") -> list[str]:
        return list(self.existing)

    async def delete_document(self, namespace: str, path: str) -> None:
        self.deleted.append(path)


class _FakeConnector:
    name = "fake"

    def __init__(self, items: dict[str, bytes], *, broken: set[str] | None = None) -> None:
        self._items = items
        self._broken = broken or set()

    def discover(self) -> list[SourceItem]:
        return [SourceItem(path=p, locator=p) for p in self._items]

    def fetch(self, item: SourceItem) -> bytes:
        if item.locator in self._broken:
            raise OSError("unreadable")
        return self._items[item.locator]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def test_ingests_new_documents() -> None:
    client = _FakeClient()
    connector = _FakeConnector({"a.md": b"alpha", "sub/b.txt": b"beta"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.ingested == 2 and report.skipped == 0
    assert {p for p, _ in client.put} == {"a.md", "sub/b.txt"}


async def test_skips_unchanged_by_checksum() -> None:
    client = _FakeClient(existing={"a.md": _sha(b"alpha")})
    connector = _FakeConnector({"a.md": b"alpha", "b.md": b"new"})
    report = await SyncEngine(client).sync(connector, "ns")
    assert report.skipped == 1 and report.ingested == 1
    assert [p for p, _ in client.put] == ["b.md"]


async def test_dry_run_writes_nothing() -> None:
    client = _FakeClient()
    connector = _FakeConnector({"a.md": b"alpha"})
    report = await SyncEngine(client, dry_run=True).sync(connector, "ns")
    assert report.ingested == 1
    assert client.put == []


async def test_prune_deletes_documents_absent_from_source() -> None:
    client = _FakeClient(existing={"gone.md": _sha(b"old")})
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
