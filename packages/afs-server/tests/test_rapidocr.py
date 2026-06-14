"""The rapidocr rung — OCR via an injected fake (no rapidocr/onnx needed). The
PDF path really rasterizes (pypdfium2 + Pillow); only the OCR call is faked."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction.rapidocr import RapidOcrNormalizer

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


def _src(name: str, content_type: str | None, path: Path | None = None) -> SourceDocument:
    p = path or Path(name)
    return SourceDocument(filename=p.name, content_type=content_type, size=0, local_path=p)


class TestRapidOcrNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> RapidOcrNormalizer:
        return RapidOcrNormalizer(ocr=lambda _image: "ocr text")

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return _src(_PDF.name, "application/pdf", _PDF)


async def test_ocrs_each_pdf_page() -> None:
    calls: list[Any] = []

    def fake(image: Any) -> str:
        calls.append(image)
        return f"page {len(calls)} text"

    result = await RapidOcrNormalizer(ocr=fake).normalize(_src("s.pdf", "application/pdf", _PDF))
    assert len(calls) == 2
    assert result.quality.page_count == 2
    assert result.quality.ocr_used is True
    assert "page 1 text" in result.pages[0].markdown


async def test_ocrs_an_image_directly(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "scan.png"
    Image.new("RGB", (12, 12), "white").save(p)
    calls: list[Any] = []

    def fake(image: Any) -> str:
        calls.append(image)
        return "from image"

    result = await RapidOcrNormalizer(ocr=fake).normalize(_src("scan.png", "image/png", p))
    assert len(calls) == 1
    assert "from image" in result.pages[0].markdown


def test_routing() -> None:
    n = RapidOcrNormalizer(ocr=lambda _i: "x")
    assert n.accepts(_src("a.pdf", "application/pdf")) is True
    assert n.accepts(_src("a.png", "image/png")) is True
    assert n.accepts(_src("a.docx", None)) is False
