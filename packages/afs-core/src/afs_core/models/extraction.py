"""Extraction DTOs (plan §5.4) — the normalized format every extractor produces
and the ingestion pipeline consumes.

A `Normalizer` (text_native, docling, llamaparse, or your own) turns a
`SourceDocument` (raw bytes staged to a file) into a `NormalizedDocument`
(per-page markdown + a quality report). The pipeline writes those pages to the
derived text layer — the normalizer never touches S3 keys or catalog rows.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    """One document to extract. The original is staged to ``local_path`` so rungs
    (e.g. Docling) can stream from disk rather than hold bytes in memory."""

    model_config = {"arbitrary_types_allowed": True}

    filename: str
    content_type: str | None
    size: int
    local_path: Path


class PageText(BaseModel):
    """One extracted page."""

    number: int  # 1-based
    markdown: str
    source_locator: str | None = None  # e.g. "pdf:page=12", "xlsx:sheet=Costs"


class QualityReport(BaseModel):
    """Signals the pipeline uses to gate/escalate (e.g. escalate to OCR/LlamaParse)."""

    page_count: int
    char_count: int
    ocr_used: bool = False
    min_chars_per_page: int = 0  # the lowest per-page char count seen


class NormalizedDocument(BaseModel):
    """A normalizer's output — the format the ingestion pipeline consumes."""

    pages: list[PageText] = Field(default_factory=list)
    quality: QualityReport
