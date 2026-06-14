"""The textract rung — OCR via a faked Textract client (no AWS calls). The PDF
path really rasterizes (pypdfium2 + Pillow); only the API call is faked."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction.textract import TextractNormalizer

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


class _FakeTextract:
    def __init__(self, lines: tuple[str, ...] = ("line one", "line two")) -> None:
        self.calls = 0
        self._lines = lines

    def detect_document_text(self, Document: dict) -> dict:  # boto3 keyword
        self.calls += 1
        return {"Blocks": [{"BlockType": "LINE", "Text": t} for t in self._lines]}


def _src(name: str, content_type: str | None, path: Path | None = None) -> SourceDocument:
    p = path or Path(name)
    return SourceDocument(filename=p.name, content_type=content_type, size=0, local_path=p)


class TestTextractNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> TextractNormalizer:
        return TextractNormalizer(client=_FakeTextract())

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return _src(_PDF.name, "application/pdf", _PDF)


async def test_ocrs_each_pdf_page() -> None:
    fake = _FakeTextract(("Bill of Lading", "Cargo Manifest"))
    result = await TextractNormalizer(client=fake).normalize(_src("s.pdf", "application/pdf", _PDF))
    assert fake.calls == 2  # one Textract call per rasterized page
    assert result.quality.page_count == 2
    assert result.quality.ocr_used is True
    assert "Bill of Lading" in result.pages[0].markdown
    assert result.pages[1].source_locator == "ocr:page=2"


async def test_ocrs_an_image_directly(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "scan.png"
    Image.new("RGB", (12, 12), "white").save(p)
    fake = _FakeTextract(("hello from a scan",))
    result = await TextractNormalizer(client=fake).normalize(_src("scan.png", "image/png", p))
    assert fake.calls == 1  # image goes straight through, no rasterization
    assert "hello from a scan" in result.pages[0].markdown


async def test_reports_min_confidence() -> None:
    class _WithConfidence:
        def detect_document_text(self, Document: dict) -> dict:  # boto3 keyword
            return {
                "Blocks": [
                    {"BlockType": "LINE", "Text": "a", "Confidence": 90.0},
                    {"BlockType": "LINE", "Text": "b", "Confidence": 80.0},
                ]
            }

    result = await TextractNormalizer(client=_WithConfidence()).normalize(
        _src("s.pdf", "application/pdf", _PDF)
    )
    # each page mean = (90+80)/2/100 = 0.85; min across pages = 0.85
    assert result.quality.confidence == pytest.approx(0.85)


async def test_confidence_none_when_textract_omits_it() -> None:
    result = await TextractNormalizer(client=_FakeTextract()).normalize(
        _src("s.pdf", "application/pdf", _PDF)
    )
    assert result.quality.confidence is None


def test_routing() -> None:
    n = TextractNormalizer(client=_FakeTextract())
    assert n.accepts(_src("a.pdf", "application/pdf")) is True
    assert n.accepts(_src("a.png", "image/png")) is True
    assert n.accepts(_src("a.tiff", None)) is True
    assert n.accepts(_src("a.docx", None)) is False
    assert n.accepts(_src("a.txt", "text/plain")) is False
