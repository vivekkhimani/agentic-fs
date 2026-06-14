"""The text_native normalizer (against the afs-core conformance kit) + the pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction import DEFAULT_LADDER, build_pipeline
from afs_server.extraction.text_native import TextNativeNormalizer
from afs_server.settings import Settings


def _doc(path: Path, content_type: str) -> SourceDocument:
    return SourceDocument(
        filename=path.name,
        content_type=content_type,
        size=path.stat().st_size,
        local_path=path,
    )


class TestTextNativeNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> TextNativeNormalizer:
        return TextNativeNormalizer()

    @pytest.fixture
    def sample(self, tmp_path: Path) -> SourceDocument:
        p = tmp_path / "doc.md"
        p.write_text("# Hello\nworld")
        return _doc(p, "text/markdown")


async def test_pipeline_extracts_text(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("hello")
    outcome = await build_pipeline().run(_doc(p, "text/markdown"))
    assert outcome is not None
    assert outcome.extractor == "text_native"
    assert outcome.document.pages[0].markdown == "hello"


async def test_pipeline_binary_is_catalog_only(tmp_path: Path) -> None:
    p = tmp_path / "logo.png"
    p.write_bytes(b"\x89PNG\r\n")
    assert await build_pipeline().run(_doc(p, "image/png")) is None


async def test_pipeline_empty_text_is_catalog_only(tmp_path: Path) -> None:
    p = tmp_path / "blank.md"
    p.write_text("   \n  ")
    assert await build_pipeline().run(_doc(p, "text/markdown")) is None


def test_registry_rejects_unknown_normalizer() -> None:
    with pytest.raises(ValueError, match="unknown normalizer"):
        build_pipeline(["does-not-exist"])


def test_settings_default_ladder_matches_default_ladder() -> None:
    """The app builds its pipeline from settings (never build_pipeline(None)), so a
    drift between the settings default and DEFAULT_LADDER silently shrinks the
    inline ladder — which once made every born-digital PDF land catalog_only."""
    assert Settings().extraction_ladder_names == DEFAULT_LADDER


async def test_default_pipeline_extracts_born_digital_pdf() -> None:
    """A text-layer PDF must extract on the default (no-extra) ladder, inline."""
    pdf = Path(__file__).parent / "fixtures" / "sample.pdf"
    outcome = await build_pipeline(Settings().extraction_ladder_names).run(
        _doc(pdf, "application/pdf")
    )
    assert outcome is not None
    assert outcome.extractor == "pdf"
    assert outcome.document.pages
