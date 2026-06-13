"""The ingest write path (plan §9).

Slice 1: a direct write path — `put_document` writes the original to S3, creates
the catalog row, and runs a minimal **text_native** extraction inline (text files
become readable immediately). Binary/unsupported types land `catalog_only` (still
listed + citeable). The presigned-upload/complete flow, the event-driven
extractor (Docling), and the reconciler are later slices.
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
from afs_core.models import CatalogEntry, ExtractionState

if TYPE_CHECKING:
    from afs_core.contracts import CatalogStore, ObjectStore
    from afs_server.auth import TenantContext

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_TEXT_CONTENT_TYPES = {"application/json", "application/xml", "application/x-ndjson"}
_TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".text", ".csv", ".tsv",
    ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".log",
}  # fmt: skip


def new_ulid() -> str:
    """A ULID (Crockford base32, time-ordered) — used as the document/entry id."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def _is_text_native(content_type: str, path: str) -> bool:
    if content_type.startswith("text/") or content_type in _TEXT_CONTENT_TYPES:
        return True
    return os.path.splitext(path)[1].lower() in _TEXT_EXTENSIONS


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class IngestService:
    def __init__(self, catalog: CatalogStore, objects: ObjectStore) -> None:
        self._catalog = catalog
        self._objects = objects

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

        if _is_text_native(content_type, path):
            text = data.decode("utf-8", errors="replace")
            await self._objects.put(
                keys.derived_text_key(ctx.tenant_id, namespace, entry_id, 1),
                text.encode("utf-8"),
                content_type="text/markdown",
            )
            extraction = ExtractionState(
                status="extracted",
                page_count=1,
                extractor="text_native",
                text_checksum=_sha256(text.encode("utf-8")),
            )
        else:
            extraction = ExtractionState(status="catalog_only", reason="no_extractor")

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
