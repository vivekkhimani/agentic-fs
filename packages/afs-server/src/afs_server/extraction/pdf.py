"""The ``pdf`` rung — lightweight, reliable PDF text extraction via pypdfium2.

PDFium (Chrome's PDF engine, via a prebuilt binary wheel — no ML, no system deps)
pulls the text layer per page. Text-layer PDFs (the common case) become readable
**synchronously, in-request**. A scanned PDF has no text layer → empty pages →
the quality gate falls through to a heavier rung (docling/OCR, async).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pypdfium2 as pdfium

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport

if TYPE_CHECKING:
    from afs_core.models import SourceDocument


class PdfNormalizer:
    name = "pdf"

    def accepts(self, doc: SourceDocument) -> bool:
        return (doc.content_type or "") == "application/pdf" or (
            doc.local_path.suffix.lower() == ".pdf"
        )

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        # pypdfium2 is synchronous C — keep it off the event loop.
        return await asyncio.to_thread(self._extract_sync, str(doc.local_path))

    def _extract_sync(self, path: str) -> NormalizedDocument:
        pdf = pdfium.PdfDocument(path)
        try:
            pages: list[PageText] = []
            for index in range(len(pdf)):
                page = pdf[index]
                textpage = page.get_textpage()
                text = textpage.get_text_range()
                textpage.close()
                page.close()
                if not text.strip():
                    continue  # blank / image-only page; renumber kept pages contiguous
                pages.append(
                    PageText(
                        number=len(pages) + 1,
                        markdown=text,
                        source_locator=f"pdf:page={index + 1}",
                    )
                )
        finally:
            pdf.close()

        if not pages:
            raise NormalizationError("empty_document", "no extractable text layer")
        char_counts = [len(p.markdown) for p in pages]
        return NormalizedDocument(
            pages=pages,
            quality=QualityReport(
                page_count=len(pages),
                char_count=sum(char_counts),
                min_chars_per_page=min(char_counts),
            ),
        )
