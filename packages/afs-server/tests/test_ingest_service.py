"""IngestService write path + the ingest→read round-trip, over the in-memory fakes."""

from __future__ import annotations

import pytest

from afs_core.errors import InsufficientScopeError
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore
from afs_server.auth import TenantContext
from afs_server.extraction import build_pipeline
from afs_server.services import FsService, IngestService

_CTX = TenantContext(tenant_id="acme", principal_id="p", scopes=frozenset({"ingest", "fs:read"}))


@pytest.fixture
def services() -> tuple[IngestService, FsService]:
    catalog, objects = InMemoryCatalogStore(), InMemoryObjectStore()
    return IngestService(catalog, objects, build_pipeline()), FsService(catalog, objects)


async def test_text_document_is_ingested_and_readable(
    services: tuple[IngestService, FsService],
) -> None:
    ingest, fs = services
    entry = await ingest.put_document(
        _CTX, "handbook", "notes/intro.md", b"# Hello\nworld", content_type="text/markdown"
    )
    assert entry.extraction.status == "extracted"
    assert entry.extraction.extractor == "text_native"

    # Listed...
    page = await fs.list_entries(_CTX, "handbook")
    assert [e.path for e in page.items] == ["notes/intro.md"]
    # ...and readable end-to-end.
    read = await fs.read(_CTX, "handbook", "notes/intro.md")
    assert read.pages[0].text == "# Hello\nworld"


async def test_binary_document_lands_catalog_only(
    services: tuple[IngestService, FsService],
) -> None:
    ingest, _ = services
    entry = await ingest.put_document(
        _CTX, "handbook", "logo.png", b"\x89PNG\r\n", content_type="image/png"
    )
    assert entry.extraction.status == "catalog_only"
    assert entry.extraction.reason == "no_extractor"


async def test_reingest_reuses_entry_id(services: tuple[IngestService, FsService]) -> None:
    ingest, _ = services
    first = await ingest.put_document(_CTX, "handbook", "a.md", b"v1", content_type="text/markdown")
    second = await ingest.put_document(
        _CTX, "handbook", "a.md", b"v2", content_type="text/markdown"
    )
    assert first.entry_id == second.entry_id


async def test_delete_tombstones_and_removes_object(
    services: tuple[IngestService, FsService],
) -> None:
    ingest, fs = services
    await ingest.put_document(_CTX, "handbook", "a.md", b"hi", content_type="text/markdown")
    await ingest.delete_document(_CTX, "handbook", "a.md")
    assert (await fs.list_entries(_CTX, "handbook")).items == []


async def test_requires_ingest_scope(services: tuple[IngestService, FsService]) -> None:
    ingest, _ = services
    ctx = TenantContext(tenant_id="acme", principal_id="p", scopes=frozenset({"fs:read"}))
    with pytest.raises(InsufficientScopeError):
        await ingest.put_document(ctx, "handbook", "a.md", b"x", content_type="text/markdown")
