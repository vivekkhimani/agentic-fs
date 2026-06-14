"""Content-type routing (ADR 0010 phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_server.extraction import build_from_settings
from afs_server.extraction.routing import (
    RoutedExtractionPipeline,
    load_pipeline_file,
    select_route,
)
from afs_server.settings import Settings

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


def _doc(content_type: str, path: Path) -> SourceDocument:
    return SourceDocument(
        filename=path.name, content_type=content_type, size=path.stat().st_size, local_path=path
    )


def test_select_route_exact_prefix_default() -> None:
    routes = {"application/pdf": ["pdf"], "image/*": ["llm"], "*": ["text_native"]}
    assert select_route("application/pdf", routes) == ["pdf"]  # exact
    assert select_route("image/png", routes) == ["llm"]  # type/* prefix
    assert select_route("text/plain", routes) == ["text_native"]  # default
    assert select_route("application/pdf", {"image/*": ["llm"]}) is None  # no match, no default


async def test_routes_by_content_type(tmp_path: Path) -> None:
    md = tmp_path / "note.md"
    md.write_text("# Title\n\nbody")
    # markdown → text_native branch; pdf → pdf branch. Distinct extractors prove routing.
    routed = RoutedExtractionPipeline(
        {"text/markdown": ["text_native"], "application/pdf": ["pdf"]}, engine="ladder"
    )
    md_outcome = await routed.run(_doc("text/markdown", md))
    pdf_outcome = await routed.run(_doc("application/pdf", _PDF))
    assert md_outcome is not None and md_outcome.extractor == "text_native"
    assert pdf_outcome is not None and pdf_outcome.extractor == "pdf"


async def test_unmatched_without_default_is_catalog_only(tmp_path: Path) -> None:
    routed = RoutedExtractionPipeline({"text/markdown": ["text_native"]}, engine="ladder")
    assert await routed.run(_doc("application/pdf", _PDF)) is None


async def test_default_route_catches_the_rest() -> None:
    routed = RoutedExtractionPipeline(
        {"text/markdown": ["text_native"], "*": ["pdf"]}, engine="ladder"
    )
    outcome = await routed.run(_doc("application/pdf", _PDF))
    assert outcome is not None and outcome.extractor == "pdf"


def test_load_pipeline_file(tmp_path: Path) -> None:
    p = tmp_path / "afs-pipeline.yaml"
    p.write_text(
        "min_confidence: 0.6\n"
        "routes:\n"
        '  "image/*": [textract_analyze, llm]\n'
        '  "application/pdf": [text_native, pdf]\n'
        '  "*": [text_native, pdf, docx]\n'
    )
    cfg = load_pipeline_file(str(p))
    assert cfg.min_confidence == 0.6
    assert cfg.routes["image/*"] == ["textract_analyze", "llm"]
    assert cfg.routes["*"] == ["text_native", "pdf", "docx"]


def test_load_pipeline_file_rejects_empty(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("min_confidence: 0.5\n")
    with pytest.raises(ValueError, match="non-empty 'routes'"):
        load_pipeline_file(str(p))


async def test_build_from_settings_uses_routing_when_file_set(tmp_path: Path) -> None:
    p = tmp_path / "afs-pipeline.yaml"
    p.write_text('routes:\n  "application/pdf": [pdf]\n  "*": [text_native]\n')
    runner = build_from_settings(Settings(pipeline_file=str(p), pipeline_engine="ladder"))
    assert isinstance(runner, RoutedExtractionPipeline)
    outcome = await runner.run(_doc("application/pdf", _PDF))
    assert outcome is not None and outcome.extractor == "pdf"


def test_build_from_settings_single_ladder_without_file() -> None:
    runner = build_from_settings(Settings(pipeline_engine="ladder"))
    assert not isinstance(runner, RoutedExtractionPipeline)
