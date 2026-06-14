"""Pipeline presets + engine resolution/fallback."""

from __future__ import annotations

import sys

import pytest

from afs_server.extraction import build_pipeline
from afs_server.extraction.pipeline import ExtractionPipeline
from afs_server.extraction.presets import PRESETS, preset_ladder
from afs_server.settings import Settings


def test_preset_ladder_known_and_unknown() -> None:
    assert preset_ladder("lite") == ["text_native", "pdf", "docx"]
    assert preset_ladder("ocr")[-1] == "textract"
    with pytest.raises(ValueError, match="unknown AFS_PIPELINE_PRESET"):
        preset_ladder("nope")


def test_settings_resolves_preset_and_default() -> None:
    # default: no ladder, no preset → the lite preset
    assert Settings().extraction_ladder_names == PRESETS["lite"]
    # a named preset
    assert Settings(pipeline_preset="tables").extraction_ladder_names == PRESETS["tables"]
    # an explicit ladder overrides the preset
    s = Settings(pipeline_preset="ocr", extraction_ladder="text_native,llm")
    assert s.extraction_ladder_names == ["text_native", "llm"]


def test_default_engine_is_haystack() -> None:
    assert Settings().pipeline_engine == "haystack"


def test_unknown_preset_surfaces_on_resolution() -> None:
    with pytest.raises(ValueError, match="unknown AFS_PIPELINE_PRESET"):
        _ = Settings(pipeline_preset="bogus").extraction_ladder_names


def test_haystack_falls_back_to_ladder_when_extra_missing(monkeypatch) -> None:
    # Simulate the [haystack] extra not being installed (e.g. the slim serving
    # image): importing the engine module raises → build_pipeline runs the ladder.
    monkeypatch.setitem(sys.modules, "afs_server.extraction.haystack_engine", None)
    pipe = build_pipeline(["text_native"], engine="haystack")
    assert isinstance(pipe, ExtractionPipeline)


def test_unknown_engine_raises() -> None:
    with pytest.raises(ValueError, match="unknown AFS_PIPELINE_ENGINE"):
        build_pipeline(["text_native"], engine="nope")
