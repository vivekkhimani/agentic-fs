"""The ingest write path (plan §9, ADR 0009).

`IngestService` owns *where bytes land* (S3 keys, catalog rows); parsing is the
pluggable `ExtractionPipeline`'s job. Extraction runs either **inline**
(synchronous, in-request) or **async** — the row lands ``pending`` and the
extractor worker (`extract_object`, driven by an S3 event) completes it. The mode
is `AFS_EXTRACTION_MODE`.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from afs_core import keys
from afs_core.errors import NamespaceNotFoundError
from afs_core.models import CatalogEntry, ExtractionState, SourceRef
from afs_server.extraction import run_extraction

if TYPE_CHECKING:
    from afs_core.contracts import CatalogStore, ObjectStore
    from afs_server.auth import TenantContext
    from afs_server.extraction import ExtractionPipeline

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """A ULID (Crockford base32, time-ordered) — used as the document/entry id."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _guess_type(path: str, override: str | None = None) -> str:
    return override or mimetypes.guess_type(path)[0] or "application/octet-stream"


class IngestService:
    def __init__(
        self,
        catalog: CatalogStore,
        objects: ObjectStore,
        pipeline: ExtractionPipeline,
        *,
        extraction_mode: str = "inline",
    ) -> None:
        self._catalog = catalog
        self._objects = objects
        self._pipeline = pipeline
        self._async = extraction_mode == "async"

    def _authorize(self, ctx: TenantContext, namespace: str) -> None:
        ctx.require_scope("ingest")
        if not ctx.allows_namespace(namespace):
            raise NamespaceNotFoundError("namespace not found", detail={"namespace": namespace})

    async def put_document(
        self,
        ctx: TenantContext,
        namespace: str,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        title: str | None = None,
        source: SourceRef | None = None,
    ) -> CatalogEntry:
        self._authorize(ctx, namespace)
        keys.validate_relpath(path)

        content_type = _guess_type(path, content_type)
        now = datetime.now(UTC)

        # Reuse the existing entry_id on re-ingest so derived data isn't orphaned.
        existing = await self._catalog.get_entry(ctx.tenant_id, namespace, path)
        entry_id = existing.entry_id if existing else new_ulid()
        created_at = existing.created_at if existing else now

        stat = await self._objects.put(
            keys.originals_key(ctx.tenant_id, namespace, path), data, content_type=content_type
        )
        if self._async:
            # Defer to the worker (an S3 event will drive extract_object).
            extraction = ExtractionState(status="pending")
        else:
            extraction = await run_extraction(
                self._objects,
                self._pipeline,
                tenant_id=ctx.tenant_id,
                namespace=namespace,
                entry_id=entry_id,
                path=path,
                data=data,
                content_type=content_type,
            )

        entry = CatalogEntry(
            tenant_id=ctx.tenant_id,
            namespace=namespace,
            path=path,
            entry_id=entry_id,
            size=len(data),
            etag=stat.etag,
            checksum=_sha256(data),
            content_type=content_type,
            title=title or path.rsplit("/", 1)[-1],
            extraction=extraction,
            source=source,
            created_at=created_at,
            updated_at=now,
        )
        await self._catalog.put_entry(entry)
        return entry

    async def extract_object(self, tenant_id: str, namespace: str, path: str) -> None:
        """Worker entrypoint (ADR 0009): (re)extract the stored object and update
        its row. Reads bytes from S3 — so an object dropped directly into the
        bucket (no row yet) is indexed too. Idempotent: derived keys are
        deterministic, so a redelivery overwrites rather than duplicates.
        """
        key = keys.originals_key(tenant_id, namespace, path)
        data = await self._objects.get(key)
        stat = await self._objects.stat(key)
        content_type = _guess_type(path, stat.content_type if stat else None)

        existing = await self._catalog.get_entry(tenant_id, namespace, path)
        entry_id = existing.entry_id if existing else new_ulid()
        extraction = await run_extraction(
            self._objects,
            self._pipeline,
            tenant_id=tenant_id,
            namespace=namespace,
            entry_id=entry_id,
            path=path,
            data=data,
            content_type=content_type,
        )

        if existing is not None:
            await self._catalog.set_extraction(tenant_id, namespace, path, extraction)
            return
        now = datetime.now(UTC)
        await self._catalog.put_entry(
            CatalogEntry(
                tenant_id=tenant_id,
                namespace=namespace,
                path=path,
                entry_id=entry_id,
                size=len(data),
                etag=stat.etag if stat else "",
                checksum=_sha256(data),
                content_type=content_type,
                title=path.rsplit("/", 1)[-1],
                extraction=extraction,
                created_at=now,
                updated_at=now,
            )
        )

    async def delete_document(self, ctx: TenantContext, namespace: str, path: str) -> None:
        self._authorize(ctx, namespace)
        keys.validate_relpath(path)

        existing = await self._catalog.get_entry(ctx.tenant_id, namespace, path)
        await self._catalog.delete_entry(ctx.tenant_id, namespace, path)  # tombstone
        await self._objects.delete(keys.originals_key(ctx.tenant_id, namespace, path))
        if existing is not None:
            await self._objects.delete_prefix(
                f"derived/text/{ctx.tenant_id}/{namespace}/{existing.entry_id}/"
            )
