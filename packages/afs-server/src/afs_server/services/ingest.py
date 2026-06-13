"""The ingest write path (plan §9).

The pipeline owns *where bytes land* (S3 keys, catalog rows, derived layout); the
parsing is delegated to the pluggable `ExtractionPipeline` (a ladder of
`Normalizer`s) — `IngestService` never parses a document itself. (Extraction is
synchronous here for the in-request slice; the event-driven extractor worker that
runs the same pipeline off SQS is a later slice.)
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from afs_core import keys
from afs_core.errors import NamespaceNotFoundError
from afs_core.models import CatalogEntry, ExtractionState, SourceDocument

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


class IngestService:
    def __init__(
        self, catalog: CatalogStore, objects: ObjectStore, pipeline: ExtractionPipeline
    ) -> None:
        self._catalog = catalog
        self._objects = objects
        self._pipeline = pipeline

    def _authorize(self, ctx: TenantContext, namespace: str) -> None:
        ctx.require_scope("ingest")
        if not ctx.allows_namespace(namespace):
            raise NamespaceNotFoundError("namespace not found", detail={"namespace": namespace})

    async def _extract(
        self,
        ctx: TenantContext,
        namespace: str,
        entry_id: str,
        path: str,
        data: bytes,
        content_type: str,
    ) -> ExtractionState:
        """Run the pluggable pipeline over a staged copy and write the derived pages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            staged = Path(tmpdir) / (path.rsplit("/", 1)[-1] or "doc")
            staged.write_bytes(data)
            outcome = await self._pipeline.run(
                SourceDocument(
                    filename=staged.name,
                    content_type=content_type,
                    size=len(data),
                    local_path=staged,
                )
            )

        if outcome is None:
            return ExtractionState(status="catalog_only", reason="no_extractor")

        all_text = []
        for page in outcome.document.pages:
            await self._objects.put(
                keys.derived_text_key(ctx.tenant_id, namespace, entry_id, page.number),
                page.markdown.encode("utf-8"),
                content_type="text/markdown",
            )
            all_text.append(page.markdown)
        return ExtractionState(
            status="extracted",
            page_count=len(outcome.document.pages),
            extractor=outcome.extractor,
            text_checksum=_sha256("\n".join(all_text).encode("utf-8")),
        )

    async def put_document(
        self,
        ctx: TenantContext,
        namespace: str,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        title: str | None = None,
    ) -> CatalogEntry:
        self._authorize(ctx, namespace)
        keys.validate_relpath(path)

        content_type = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
        now = datetime.now(UTC)

        # Reuse the existing entry_id on re-ingest so derived data isn't orphaned.
        existing = await self._catalog.get_entry(ctx.tenant_id, namespace, path)
        entry_id = existing.entry_id if existing else new_ulid()
        created_at = existing.created_at if existing else now

        stat = await self._objects.put(
            keys.originals_key(ctx.tenant_id, namespace, path), data, content_type=content_type
        )
        extraction = await self._extract(ctx, namespace, entry_id, path, data, content_type)

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
            created_at=created_at,
            updated_at=now,
        )
        await self._catalog.put_entry(entry)
        return entry

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
