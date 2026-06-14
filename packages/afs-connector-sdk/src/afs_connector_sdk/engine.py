"""The source-agnostic sync engine (ADR 0007, 0008).

Per item: skip the **fetch** when the source change-token matches what we stored
last run (L1); otherwise fetch and skip the **ingest** when the content checksum
matches (so nothing is re-extracted needlessly). A connector with a native delta
feed (`IncrementalConnector`) takes the cheaper path — only changed items + a
persisted cursor (L2) — and the engine applies the deletes it reports. For
full-scan connectors, ``prune`` mirrors deletes via set difference.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from afs_core.contracts import IncrementalConnector

if TYPE_CHECKING:
    from afs_connector_sdk.client import IngestClient
    from afs_core.contracts import Connector
    from afs_core.models import SourceItem


@dataclass
class SyncReport:
    ingested: int = 0
    skipped: int = 0
    deleted: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class SyncEngine:
    def __init__(
        self,
        client: IngestClient,
        *,
        concurrency: int = 8,
        prune: bool = False,
        dry_run: bool = False,
    ) -> None:
        self._client = client
        self._sem = asyncio.Semaphore(concurrency)
        self._prune = prune
        self._dry = dry_run

    async def sync(self, connector: Connector, namespace: str) -> SyncReport:
        report = SyncReport()
        if isinstance(connector, IncrementalConnector):
            await self._sync_incremental(connector, namespace, report)
        else:
            await self._sync_full(connector, namespace, report)
        return report

    async def _sync_full(self, connector: Connector, namespace: str, report: SyncReport) -> None:
        items = list(connector.discover())
        await asyncio.gather(*(self._process(connector, namespace, it, report) for it in items))
        if self._prune:
            seen = {it.path for it in items}
            await self._prune_missing(namespace, seen, report)

    async def _sync_incremental(
        self, connector: IncrementalConnector, namespace: str, report: SyncReport
    ) -> None:
        cursor = await self._client.get_checkpoint(connector.name)
        changes = await asyncio.to_thread(connector.discover_changes, cursor)
        await asyncio.gather(
            *(self._process(connector, namespace, it, report) for it in changes.items)
        )
        for path in changes.deleted:
            await self._delete(namespace, path, report)
        if not self._dry:
            await self._client.put_checkpoint(connector.name, changes.cursor)

    async def _process(
        self, connector: Connector, namespace: str, item: SourceItem, report: SyncReport
    ) -> None:
        async with self._sem:
            try:
                existing = await self._client.stat(namespace, item.path)
                # L1: same source version as last sync → skip the fetch entirely.
                if existing and item.version and self._stored_version(existing) == item.version:
                    report.skipped += 1
                    return
                data = await asyncio.to_thread(connector.fetch, item)
                checksum = hashlib.sha256(data).hexdigest()
                # Content unchanged → skip the (re-)ingest + extraction.
                if existing and existing.get("checksum") == checksum:
                    report.skipped += 1
                    return
                if not self._dry:
                    await self._client.put_document(
                        namespace,
                        item.path,
                        data,
                        content_type=item.content_type,
                        connector_id=connector.name,
                        remote_id=item.locator,
                        source_version=item.version,
                    )
                report.ingested += 1
            except Exception as err:
                report.failed += 1
                report.errors.append(f"{item.path}: {err}")

    @staticmethod
    def _stored_version(entry: dict) -> str | None:
        return (entry.get("source") or {}).get("version")

    async def _prune_missing(self, namespace: str, seen: set[str], report: SyncReport) -> None:
        try:
            existing = await self._client.list_paths(namespace)
        except Exception as err:
            report.errors.append(f"prune-list: {err}")
            return
        for path in existing:
            if path not in seen:
                await self._delete(namespace, path, report)

    async def _delete(self, namespace: str, path: str, report: SyncReport) -> None:
        if self._dry:
            report.deleted += 1
            return
        try:
            await self._client.delete_document(namespace, path)
            report.deleted += 1
        except Exception as err:
            report.failed += 1
            report.errors.append(f"delete {path}: {err}")
