"""The reconciler — heal catalog drift from S3 (the "rebuildable from S3" promise).

Events (S3 -> EventBridge -> SQS -> worker) keep the catalog in sync, but events
can be missed, the worker can fail past the DLQ, and objects can be dropped into
or deleted from S3 directly. This scheduled sweep diffs S3 against the catalog and
heals both directions:

- **object present, no / tombstoned / stale row** -> enqueue it on the extract
  queue so the worker (re)extracts. A tombstoned row reappearing is how a deleted-
  then-re-added file comes back to life.
- **live row, object gone** -> **soft-delete** (tombstone). Never a hard delete:
  tombstones are reversible (the row, its entry_id and history survive), so a file
  that returns is revived rather than recreated from nothing.

The reconciler only *detects* drift; the worker does the extraction. It touches
only ``tenants/`` originals (derived/scratch keys are skipped). S3 is canonical.
See ADR 0011 for the full state table and the soft-delete/revival rationale.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from afs_core import keys

if TYPE_CHECKING:
    from afs_core.contracts import CatalogStore, ObjectStore
    from afs_core.models import CatalogEntry, ObjectStat

logger = logging.getLogger("afs_server.reconcile")

# An original key -> "please (re)extract this". The handler sends it to the extract
# SQS queue; tests collect it.
EnqueueFn = Callable[[str], Awaitable[None]]

# Don't tombstone a row whose object we can't see if the row was written very
# recently — guards against racing a fresh write / a stale list snapshot.
DEFAULT_GRACE_SECONDS = 900


@dataclass
class ReconcileReport:
    namespaces: int = 0
    objects: int = 0
    live_rows: int = 0
    enqueued: int = 0  # drift -> (re)extract
    tombstoned: int = 0  # orphaned rows soft-deleted
    in_sync: int = 0


def _norm_etag(etag: str | None) -> str:
    return (etag or "").strip().strip('"')


async def reconcile(
    catalog: CatalogStore,
    objects: ObjectStore,
    enqueue: EnqueueFn,
    *,
    grace_seconds: int = DEFAULT_GRACE_SECONDS,
    now: datetime | None = None,
) -> ReconcileReport:
    """Diff S3 against the catalog and heal drift. Idempotent."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=grace_seconds)
    report = ReconcileReport()

    grouped = await _grouped_originals(objects)
    pairs = set(grouped) | await _catalog_namespaces(catalog)
    report.namespaces = len(pairs)

    for tenant_id, namespace in sorted(pairs):
        s3_objects = grouped.get((tenant_id, namespace), {})
        rows = await _namespace_rows(catalog, tenant_id, namespace)
        report.objects += len(s3_objects)
        report.live_rows += sum(1 for e in rows.values() if e.deleted_at is None)

        # Direction 1: every S3 original should have a current, live row.
        for path, stat in s3_objects.items():
            entry = rows.get(path)
            if entry is None or entry.deleted_at is not None:
                await enqueue(keys.originals_key(tenant_id, namespace, path))
                report.enqueued += 1
            elif _norm_etag(entry.etag) != _norm_etag(stat.etag):
                await enqueue(keys.originals_key(tenant_id, namespace, path))  # object changed
                report.enqueued += 1
            else:
                report.in_sync += 1

        # Direction 2: a live row whose object is gone is orphaned -> tombstone it
        # (soft), once it's past the grace window.
        for path, entry in rows.items():
            if entry.deleted_at is not None or path in s3_objects:
                continue
            if entry.updated_at > cutoff:
                continue  # too fresh; revisit next sweep
            await catalog.delete_entry(tenant_id, namespace, path)  # soft (hard=False)
            report.tombstoned += 1

    logger.info("reconcile complete: %s", asdict(report))
    return report


def handler(event: object = None, context: object = None) -> dict:
    """Lambda entrypoint (scheduled by EventBridge). Reads stores + the extract
    queue from settings, sweeps, and enqueues drift; returns the report."""
    import asyncio
    import json

    import boto3

    from afs_server.logging_config import configure_logging
    from afs_server.settings import load_settings
    from afs_server.stores import get_catalog_store, get_object_store

    settings = load_settings()
    configure_logging(settings.log_level)
    if not settings.extract_queue_url:
        raise RuntimeError("AFS_EXTRACT_QUEUE_URL is required for the reconciler")

    catalog = get_catalog_store(settings)
    objects = get_object_store(settings)
    sqs = boto3.client("sqs", region_name=settings.region)
    queue_url = settings.extract_queue_url

    async def enqueue(key: str) -> None:
        # Same shape the worker parses (EventBridge "Object Created").
        await asyncio.to_thread(
            sqs.send_message,
            QueueUrl=queue_url,
            MessageBody=json.dumps({"detail": {"object": {"key": key}}}),
        )

    report = asyncio.run(
        reconcile(catalog, objects, enqueue, grace_seconds=settings.reconcile_grace_seconds)
    )
    return asdict(report)


async def _grouped_originals(
    objects: ObjectStore,
) -> dict[tuple[str, str], dict[str, ObjectStat]]:
    """All ``tenants/`` originals grouped by (tenant, namespace) -> {path: stat}."""
    grouped: dict[tuple[str, str], dict[str, ObjectStat]] = {}
    cursor: str | None = None
    while True:
        page = await objects.list("tenants/", cursor=cursor)
        for stat in page.items:
            parsed = keys.parse_key(stat.key)
            if parsed is None or not keys.is_indexable(stat.key):
                continue
            if not (parsed.namespace and parsed.path):
                continue
            grouped.setdefault((parsed.tenant_id, parsed.namespace), {})[parsed.path] = stat
        cursor = page.next_cursor
        if not cursor:
            return grouped


async def _catalog_namespaces(catalog: CatalogStore) -> set[tuple[str, str]]:
    """(tenant, namespace) pairs known to the catalog — so namespaces whose objects
    are all gone (only orphaned rows remain) are still swept."""
    pairs: set[tuple[str, str]] = set()
    cursor: str | None = None
    while True:
        page = await catalog.list_tenants(cursor=cursor)
        for tenant in page.items:
            for ns in await catalog.list_namespaces(tenant.tenant_id):
                pairs.add((tenant.tenant_id, ns.name))
        cursor = page.next_cursor
        if not cursor:
            return pairs


async def _namespace_rows(
    catalog: CatalogStore, tenant_id: str, namespace: str
) -> dict[str, CatalogEntry]:
    rows: dict[str, CatalogEntry] = {}
    cursor: str | None = None
    while True:
        page = await catalog.list_entries(tenant_id, namespace, cursor=cursor, include_deleted=True)
        for entry in page.items:
            rows[entry.path] = entry
        cursor = page.next_cursor
        if not cursor:
            return rows
