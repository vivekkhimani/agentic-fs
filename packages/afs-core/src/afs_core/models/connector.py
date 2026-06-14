"""Connector DTOs (plan §8) — the source-agnostic shape a connector yields.

A connector enumerates documents from an external source (a folder, an S3
prefix, Google Drive, …) as ``SourceItem``s; the sync engine maps each to an
agentic-fs ``{namespace}/{path}`` and ingests it. The connector never speaks to
S3 keys or the catalog — exactly like a `Normalizer` never speaks to storage.
"""

from __future__ import annotations

from pydantic import BaseModel


class SourceItem(BaseModel):
    """One document discovered at a source.

    ``path`` is the POSIX-relative path within the source — it becomes the
    document's path in agentic-fs. ``locator`` is the opaque handle the connector
    uses to fetch the bytes (an absolute path, an S3 key, a Drive file id);
    callers never interpret it. ``version`` is a cheap change token (etag / mtime
    / revision) used for provenance and change detection.
    """

    path: str
    locator: str
    size: int | None = None
    content_type: str | None = None
    version: str | None = None
