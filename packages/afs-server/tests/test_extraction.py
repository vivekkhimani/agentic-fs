"""The text_native normalizer (against the afs-core conformance kit) + the pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction import build_pipeline
from afs_server.extraction.text_native import TextNativeNormalizer


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
