"""The llm rung — multimodal extraction with an injected transcriber (no network).

The PDF path really rasterizes (pypdfium2 + Pillow); only the model call is faked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction.llm import LlmNormalizer

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


class _FakeTranscriber:
    def __init__(self, text: str = "# Page\n\n[Figure: a pump diagram]") -> None:
        self.calls = 0
        self._text = text

    def __call__(self, png: bytes) -> str:
        self.calls += 1
        assert isinstance(png, bytes) and png  # real rasterized bytes
        return self._text


def _src(name: str, content_type: str | None, path: Path | None = None) -> SourceDocument:
    p = path or Path(name)
    return SourceDocument(filename=p.name, content_type=content_type, size=0, local_path=p)


class TestLlmNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> LlmNormalizer:
        return LlmNormalizer(transcribe=_FakeTranscriber())

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return _src(_PDF.name, "application/pdf", _PDF)


async def test_one_vision_call_per_pdf_page() -> None:
    fake = _FakeTranscriber("Transcribed page.\n\n[Figure: a gravity drain tank]")
    result = await LlmNormalizer(transcribe=fake).normalize(_src("s.pdf", "application/pdf", _PDF))
    assert fake.calls == 2  # one call per rasterized page
    assert result.quality.page_count == 2
    assert result.quality.ocr_used is True
    assert "[Figure: a gravity drain tank]" in result.pages[0].markdown
    assert result.pages[1].source_locator == "llm:page=2"


async def test_image_goes_straight_through(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "scan.png"
    Image.new("RGB", (12, 12), "white").save(p)
    fake = _FakeTranscriber("hello from a diagram")
    result = await LlmNormalizer(transcribe=fake).normalize(_src("scan.png", "image/png", p))
    assert fake.calls == 1  # no rasterization for an image
    assert "hello from a diagram" in result.pages[0].markdown


async def test_blank_transcription_is_catalog_only() -> None:
    from afs_core.contracts import NormalizationError

    with pytest.raises(NormalizationError):
        await LlmNormalizer(transcribe=lambda _png: "   ").normalize(
            _src("s.pdf", "application/pdf", _PDF)
        )


def test_routing() -> None:
    n = LlmNormalizer(transcribe=_FakeTranscriber())
    assert n.accepts(_src("a.pdf", "application/pdf")) is True
    assert n.accepts(_src("a.png", "image/png")) is True
    assert n.accepts(_src("a.webp", None)) is True
    assert n.accepts(_src("a.docx", None)) is False


def test_provider_and_model_defaults(monkeypatch) -> None:
    monkeypatch.delenv("AFS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AFS_LLM_MODEL", raising=False)
    n = LlmNormalizer(transcribe=_FakeTranscriber())
    assert n._provider == "anthropic"
    assert n._model == "claude-sonnet-4-6"

    monkeypatch.setenv("AFS_LLM_PROVIDER", "openai")
    assert LlmNormalizer(transcribe=_FakeTranscriber())._model == "gpt-4o"

    monkeypatch.setenv("AFS_LLM_MODEL", "custom-model")
    assert LlmNormalizer(transcribe=_FakeTranscriber())._model == "custom-model"
