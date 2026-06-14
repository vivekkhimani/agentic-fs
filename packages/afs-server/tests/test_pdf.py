"""The pdf rung (pypdfium2) — conformance + real text-layer extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction import build_pipeline
from afs_server.extraction.pdf import PdfNormalizer

_FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def _src(name: str, content_type: str | None, path: Path | None = None) -> SourceDocument:
    p = path or Path(name)
    return SourceDocument(filename=p.name, content_type=content_type, size=0, local_path=p)


class TestPdfNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> PdfNormalizer:
        return PdfNormalizer()

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return _src(_FIXTURE.name, "application/pdf", _FIXTURE)


async def test_extracts_text_layer_per_page() -> None:
    result = await PdfNormalizer().normalize(_src("sample.pdf", "application/pdf", _FIXTURE))
    assert result.quality.page_count == 2
    assert "Agentic-FS Docling Fixture" in result.pages[0].markdown
    assert "Second Page" in result.pages[1].markdown
    assert result.pages[1].source_locator == "pdf:page=2"


async def test_pipeline_routes_pdf_to_the_pdf_rung() -> None:
    outcome = await build_pipeline().run(_src("sample.pdf", "application/pdf", _FIXTURE))
    assert outcome is not None and outcome.extractor == "pdf"


def test_rejects_non_pdf() -> None:
    assert PdfNormalizer().accepts(_src("a.txt", "text/plain")) is False
    assert PdfNormalizer().accepts(_src("a.md", "text/markdown")) is False
