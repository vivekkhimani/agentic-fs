"""The ``pdftables`` rung — richer born-digital PDF extraction via pdfplumber.

An alternative to the lightweight `pdf` rung (pypdfium2) for PDFs whose **tables**
matter: pdfplumber detects table structure and renders it as markdown tables,
alongside the page text. Still pure-Python (no ML), MIT-licensed. Use it *instead
of* `pdf` in the ladder when table fidelity beats raw speed. Needs `[pdftables]`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport

if TYPE_CHECKING:
    from afs_core.models import SourceDocument


class PdfTablesNormalizer:
    name = "pdftables"

    def accepts(self, doc: SourceDocument) -> bool:
        return (doc.content_type or "") == "application/pdf" or (
            doc.local_path.suffix.lower() == ".pdf"
        )

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        return await asyncio.to_thread(self._extract_sync, str(doc.local_path))

    def _extract_sync(self, path: str) -> NormalizedDocument:
        try:
            import pdfplumber
        except ModuleNotFoundError as err:  # pragma: no cover - import guard
            raise RuntimeError(
                "the pdftables rung needs the optional extra: pip install 'afs-server[pdftables]'"
            ) from err

        pages: list[PageText] = []
        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages):
                parts = []
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text)
                for table in page.extract_tables():
                    rendered = _table_to_markdown(table)
                    if rendered:
                        parts.append(rendered)
                markdown = "\n\n".join(parts)
                if not markdown.strip():
                    continue  # blank / image-only page; keep numbering contiguous
                pages.append(
                    PageText(
                        number=len(pages) + 1,
                        markdown=markdown,
                        source_locator=f"pdf:page={index + 1}",
                    )
                )

        if not pages:
            raise NormalizationError("empty_document", "no extractable text or tables")
        char_counts = [len(p.markdown) for p in pages]
        return NormalizedDocument(
            pages=pages,
            quality=QualityReport(
                page_count=len(pages),
                char_count=sum(char_counts),
                min_chars_per_page=min(char_counts),
            ),
        )


def _table_to_markdown(table: list[list[str | None]]) -> str:
    rows = [[(cell or "").strip() for cell in row] for row in table if row]
    if not rows:
        return ""
    header, *body = rows
    width = len(header)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
