"""The ``docling`` rung — rich extraction for PDFs, Office docs, and images.

[Docling](https://github.com/docling-project/docling) parses binary documents
(PDF / DOCX / PPTX / XLSX / images) into per-page markdown and runs OCR on scanned
PDFs. It pulls heavy ML dependencies, so it is an **optional extra**:

    pip install afs-server[docling]

and is opt-in via the ladder (``AFS_EXTRACTION_LADDER=text_native,docling``). The
serving Lambda runs ``text_native`` only; the heavier rung belongs in the
extractor worker (a later slice) so it never blocks a request.

Two deliberate choices:

- **Lazy import.** This module imports without docling installed, and ``accepts``
  is a pure routing decision (extension / MIME). The converter — and the model
  load — only happen on the first ``normalize`` call.
- **Contiguous pages.** The read path serves derived pages ``1..page_count``
  with no gaps, so this rung emits pages renumbered sequentially and records the
  *original* source page in ``source_locator`` (``page=N``). Blank pages are
  dropped (they carry no citable text and would otherwise fail the quality gate).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport

if TYPE_CHECKING:
    from afs_core.models import SourceDocument

# Formats docling handles that text_native does not. text_native takes the
# text-like formats first in the ladder, so docling only ever sees binary docs.
_DOCLING_EXTENSIONS = {
    ".pdf",
    ".docx", ".pptx", ".xlsx",
    ".doc", ".ppt", ".xls",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
}  # fmt: skip
_DOCLING_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.ms-powerpoint",
    "application/vnd.ms-excel",
}


class DoclingNormalizer:
    name = "docling"

    def __init__(self) -> None:
        self._converter: Any = None  # built lazily on first normalize()

    def accepts(self, doc: SourceDocument) -> bool:
        ct = doc.content_type or ""
        if ct in _DOCLING_CONTENT_TYPES or ct.startswith("image/"):
            return True
        return doc.local_path.suffix.lower() in _DOCLING_EXTENSIONS

    def _converter_or_load(self) -> Any:
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter
            except ModuleNotFoundError as err:  # pragma: no cover - import guard
                raise RuntimeError(
                    "the 'docling' extraction rung requires the optional dependency; "
                    "install it with `pip install afs-server[docling]`"
                ) from err
            self._converter = DocumentConverter()
        return self._converter

    def _convert_sync(self, path: str) -> NormalizedDocument:
        result = self._converter_or_load().convert(path)

        # Status is an enum; compare by name to avoid coupling to its import path.
        if getattr(getattr(result, "status", None), "name", None) == "FAILURE":
            raise NormalizationError("parse_failed", "docling failed to parse the document")

        document = result.document
        num_pages = _page_count(document)

        pages: list[PageText] = []
        if num_pages > 0:
            for source_page in range(1, num_pages + 1):
                md = document.export_to_markdown(page_no=source_page)
                if not md.strip():
                    continue  # drop blank pages; keep numbering contiguous
                pages.append(
                    PageText(
                        number=len(pages) + 1,
                        markdown=md,
                        source_locator=f"page={source_page}",
                    )
                )
        else:
            md = document.export_to_markdown()
            if md.strip():
                pages.append(PageText(number=1, markdown=md, source_locator="page=1"))

        if not pages:
            raise NormalizationError("empty_document", "docling extracted no text")

        char_counts = [len(p.markdown) for p in pages]
        return NormalizedDocument(
            pages=pages,
            quality=QualityReport(
                page_count=len(pages),
                char_count=sum(char_counts),
                ocr_used=False,
                min_chars_per_page=min(char_counts),
            ),
        )

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        # Docling is synchronous and CPU/ML-heavy — keep it off the event loop.
        return await asyncio.to_thread(self._convert_sync, str(doc.local_path))


def _page_count(document: Any) -> int:
    """Page count, tolerant of docling exposing ``num_pages`` as a method, an int
    property, or only a ``pages`` collection."""
    num_pages: Any = getattr(document, "num_pages", None)
    if callable(num_pages):
        return int(num_pages())
    if isinstance(num_pages, int):
        return num_pages
    pages: Any = getattr(document, "pages", None)
    return len(pages) if pages else 0
