"""The pdftables rung — real pdfplumber extraction over the sample PDF."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction.pdftables import PdfTablesNormalizer, _table_to_markdown

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


def _src(name: str, content_type: str | None, path: Path | None = None) -> SourceDocument:
    p = path or Path(name)
    return SourceDocument(filename=p.name, content_type=content_type, size=0, local_path=p)


class TestPdfTablesNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> PdfTablesNormalizer:
        return PdfTablesNormalizer()

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return _src(_PDF.name, "application/pdf", _PDF)


async def test_extracts_text_per_page() -> None:
    result = await PdfTablesNormalizer().normalize(_src("s.pdf", "application/pdf", _PDF))
    assert result.quality.page_count == 2
    page1 = result.pages[0].markdown
    assert "Agentic-FS" in page1 or "Docling Fixture" in page1


def test_table_to_markdown() -> None:
    md = _table_to_markdown([["Region", "Revenue"], ["EMEA", "1.2M"], ["APAC", "0.9M"]])
    assert "| Region | Revenue |" in md
    assert "| --- | --- |" in md
    assert "| EMEA | 1.2M |" in md


def test_rejects_non_pdf() -> None:
    n = PdfTablesNormalizer()
    assert n.accepts(_src("a.txt", "text/plain")) is False
    assert n.accepts(_src("a.docx", None)) is False
