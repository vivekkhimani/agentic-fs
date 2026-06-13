"""Tests for the core DTOs."""

from __future__ import annotations

from datetime import UTC, datetime

from afs_core.models import CatalogEntry, ExtractionState, Page


def _entry(**over: object) -> CatalogEntry:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    base: dict[str, object] = {
        "tenant_id": "acme",
        "namespace": "handbook",
        "path": "a.pdf",
        "entry_id": "01JABCDEF",
        "size": 10,
        "etag": "e",
        "checksum": "sha",
        "content_type": "application/pdf",
        "title": "A",
        "extraction": ExtractionState(status="extracted", page_count=3),
        "created_at": now,
        "updated_at": now,
    }
    base.update(over)
    return CatalogEntry(**base)  # type: ignore[arg-type]


def test_catalog_entry_defaults() -> None:
    entry = _entry()
    assert entry.metadata == {}
    assert entry.source is None
    assert entry.deleted_at is None
    assert entry.extraction.status == "extracted"


def test_catalog_only_is_representable() -> None:
    entry = _entry(extraction=ExtractionState(status="catalog_only", reason="encrypted_pdf"))
    assert entry.extraction.status == "catalog_only"
    assert entry.extraction.reason == "encrypted_pdf"


def test_page_is_generic_and_serializes() -> None:
    page: Page[CatalogEntry] = Page(items=[_entry()], next_cursor="abc")
    assert len(page.items) == 1
    assert page.next_cursor == "abc"
    dumped = page.model_dump()
    assert dumped["items"][0]["tenant_id"] == "acme"
    assert dumped["next_cursor"] == "abc"


def test_page_empty_default_cursor() -> None:
    page: Page[int] = Page(items=[])
    assert page.next_cursor is None
