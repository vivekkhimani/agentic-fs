"""Async extractor worker + async-mode ingest (ADR 0009), with in-memory stores."""

from __future__ import annotations

from afs_core import keys
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.auth import TenantContext
from afs_server.extraction import build_pipeline
from afs_server.services import IngestService
from afs_server.worker import object_keys_from_event, process_keys


def _stores() -> tuple[InMemoryCatalogStore, InMemoryObjectStore]:
    return InMemoryCatalogStore(), InMemoryObjectStore()


def _ingest(catalog, objects, **kw) -> IngestService:
    return IngestService(catalog, objects, build_pipeline(), **kw)


# --- event parsing ---


def test_parses_eventbridge_keys() -> None:
    event = {"Records": [{"body": '{"detail": {"object": {"key": "tenants/dev/ns/a%20b.md"}}}'}]}
    assert object_keys_from_event(event) == ["tenants/dev/ns/a b.md"]


def test_parses_direct_s3_keys() -> None:
    event = {
        "Records": [{"body": '{"Records": [{"s3": {"object": {"key": "tenants/dev/ns/x.md"}}}]}'}]
    }
    assert object_keys_from_event(event) == ["tenants/dev/ns/x.md"]


def test_skips_malformed_records() -> None:
    assert object_keys_from_event({"Records": [{"body": "not-json"}, {}]}) == []


# --- extract on event ---


async def test_completes_a_pending_row() -> None:
    catalog, objects = _stores()
    await objects.put(
        keys.originals_key("dev", "ns", "n.md"), b"# hi", content_type="text/markdown"
    )
    await catalog.put_entry(
        make_entry("dev", "ns", "n.md", entry_id="E1", extraction=ExtractionState(status="pending"))
    )

    processed = await process_keys(
        _ingest(catalog, objects), [keys.originals_key("dev", "ns", "n.md")]
    )

    assert processed == 1
    entry = await catalog.get_entry("dev", "ns", "n.md")
    assert entry is not None and entry.extraction.status == "extracted"
    # derived page written under the row's existing entry_id
    assert await objects.get(keys.derived_text_key("dev", "ns", "E1", 1)) == b"# hi"


async def test_indexes_an_object_dropped_straight_into_s3() -> None:
    catalog, objects = _stores()
    await objects.put(
        keys.originals_key("dev", "ns", "drop.md"), b"hello", content_type="text/markdown"
    )

    await process_keys(_ingest(catalog, objects), [keys.originals_key("dev", "ns", "drop.md")])

    entry = await catalog.get_entry("dev", "ns", "drop.md")
    assert entry is not None and entry.extraction.status == "extracted"


async def test_redelivery_is_idempotent() -> None:
    catalog, objects = _stores()
    key = keys.originals_key("dev", "ns", "x.md")
    await objects.put(key, b"hello", content_type="text/markdown")
    ingest = _ingest(catalog, objects)
    await process_keys(ingest, [key])
    await process_keys(ingest, [key])  # again — must not error or duplicate
    page = await catalog.list_entries("dev", "ns")
    assert len([e for e in page.items if e.path == "x.md"]) == 1


async def test_skips_non_original_keys() -> None:
    catalog, objects = _stores()
    processed = await process_keys(
        _ingest(catalog, objects),
        [keys.derived_text_key("dev", "ns", "E1", 1), "scratch/dev/p/x.md", "garbage"],
    )
    assert processed == 0


async def test_worker_skips_rows_already_extracted_inline() -> None:
    catalog, objects = _stores()
    await objects.put(
        keys.originals_key("dev", "ns", "done.md"), b"hi", content_type="text/markdown"
    )
    # serving already extracted this inline → the escalation worker must leave it.
    await catalog.put_entry(
        make_entry(
            "dev", "ns", "done.md", entry_id="E9", extraction=ExtractionState(status="extracted")
        )
    )
    await process_keys(_ingest(catalog, objects), [keys.originals_key("dev", "ns", "done.md")])
    # no derived page written by the worker — it returned before re-extracting.
    assert await objects.stat(keys.derived_text_key("dev", "ns", "E9", 1)) is None


# --- async-mode ingest ---


async def test_async_mode_writes_a_pending_row_only() -> None:
    catalog, objects = _stores()
    ingest = _ingest(catalog, objects, extraction_mode="async")
    ctx = TenantContext(tenant_id="dev", principal_id="p", scopes=frozenset({"ingest"}))

    entry = await ingest.put_document(ctx, "ns", "a.md", b"# hi", content_type="text/markdown")

    assert entry.extraction.status == "pending"
    assert await objects.get(keys.originals_key("dev", "ns", "a.md")) == b"# hi"
    # nothing extracted yet — no derived page
    assert await objects.stat(keys.derived_text_key("dev", "ns", entry.entry_id, 1)) is None
