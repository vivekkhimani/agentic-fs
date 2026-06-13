"""Core data-plane DTOs (plan §5.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Page[T](BaseModel):
    """Opaque-cursor pagination, used everywhere a list can exceed one page."""

    items: list[T]
    next_cursor: str | None = None


class ExtractionState(BaseModel):
    """The extraction lifecycle of one document.

    ``catalog_only`` is a first-class status, never a missing row — a document we
    can't extract is still listed and cite-able (plan §2.1, §5.1).
    """

    status: Literal["pending", "extracting", "extracted", "catalog_only"]
    reason: str | None = None  # closed vocabulary (events v1)
    page_count: int | None = None
    text_checksum: str | None = None
    extractor: str | None = None  # which rung produced it


class SourceRef(BaseModel):
    """Connector provenance for an ingested document."""

    connector_id: str
    remote_id: str
    version: str | None = None  # etag/revision for change detection


class CatalogEntry(BaseModel):
    """The catalog's record of one document — a derived index entry over S3."""

    tenant_id: str
    namespace: str
    path: str

    entry_id: str  # ULID
    size: int
    etag: str
    checksum: str
    content_type: str

    title: str
    metadata: dict[str, str] = Field(default_factory=dict)
    extraction: ExtractionState
    source: SourceRef | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
