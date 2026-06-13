"""The text_native rung — the first (and cheapest) Normalizer.

Markdown/text/csv/json/html/… are already text, so "extraction" is just reading
the bytes as one page. The richer rungs (docling for PDFs/Office, llamaparse on
quality failure) are additional `Normalizer`s registered the same way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport

if TYPE_CHECKING:
    from afs_core.models import SourceDocument

_TEXT_CONTENT_TYPES = {"application/json", "application/xml", "application/x-ndjson"}
_TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".text", ".csv", ".tsv",
    ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".log",
}  # fmt: skip


class TextNativeNormalizer:
    name = "text_native"

    def accepts(self, doc: SourceDocument) -> bool:
        ct = doc.content_type or ""
        if ct.startswith("text/") or ct in _TEXT_CONTENT_TYPES:
            return True
        return doc.local_path.suffix.lower() in _TEXT_EXTENSIONS

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        text = doc.local_path.read_bytes().decode("utf-8", errors="replace")
        if not text.strip():
            raise NormalizationError("empty_document")
        return NormalizedDocument(
            pages=[PageText(number=1, markdown=text, source_locator="text:1")],
            quality=QualityReport(page_count=1, char_count=len(text), min_chars_per_page=len(text)),
        )
