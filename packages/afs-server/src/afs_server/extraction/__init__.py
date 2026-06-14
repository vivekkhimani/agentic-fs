"""Extraction — the pluggable parser layer.

A `Normalizer` (text_native builtin, or a third-party plugin) is selected by name
into a ladder, exactly like the store registry. Add your own parser: implement
`afs_core.contracts.Normalizer`, certify it with
`afs_core.testing.NormalizerConformance`, register it under the `afs.normalizers`
entry-point group, and name it in the ladder. See `docs/swap-guides/` (extraction).
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from afs_core.contracts import Normalizer
from afs_server.extraction.docling import DoclingNormalizer
from afs_server.extraction.docx import DocxNormalizer
from afs_server.extraction.llm import LlmNormalizer
from afs_server.extraction.pdf import PdfNormalizer
from afs_server.extraction.pdftables import PdfTablesNormalizer
from afs_server.extraction.pipeline import ExtractionOutcome, ExtractionPipeline, ExtractionRunner
from afs_server.extraction.rapidocr import RapidOcrNormalizer
from afs_server.extraction.runner import run_extraction
from afs_server.extraction.tesseract import TesseractNormalizer
from afs_server.extraction.text_native import TextNativeNormalizer
from afs_server.extraction.textract import TextractNormalizer
from afs_server.extraction.textract_analyze import TextractAnalyzeNormalizer

if TYPE_CHECKING:
    from afs_server.settings import Settings

logger = logging.getLogger("afs_server.extraction")

_NORMALIZER_ENTRY_GROUP = "afs.normalizers"

# Builtin normalizers: name -> factory. `text_native`/`pdf`/`docx` are
# lightweight (pure-Python / a small binary) and always available; `docling` is
# constructed only when named in the ladder, and only then needs its extra.
_BUILTIN_NORMALIZERS = {
    "text_native": TextNativeNormalizer,
    "pdf": PdfNormalizer,
    "pdftables": PdfTablesNormalizer,
    "docx": DocxNormalizer,
    "textract": TextractNormalizer,
    "textract_analyze": TextractAnalyzeNormalizer,
    "tesseract": TesseractNormalizer,
    "rapidocr": RapidOcrNormalizer,
    "docling": DoclingNormalizer,
    "llm": LlmNormalizer,
}

# Default ladder (config, not code). The lightweight rungs are always available,
# so common files (text, PDF, Word) are readable with no heavy deps. Add `docling`
# (its extra) on the heavier path via AFS_EXTRACTION_LADDER, e.g. the async worker
# runs "text_native,pdf,docx,docling" to escalate scans/complex layout.
DEFAULT_LADDER = ["text_native", "pdf", "docx"]


def _build_normalizer(name: str) -> Normalizer:
    builtin = _BUILTIN_NORMALIZERS.get(name)
    if builtin is not None:
        return builtin()
    for ep in entry_points(group=_NORMALIZER_ENTRY_GROUP):
        if ep.name == name:
            return ep.load()()
    available = sorted(_BUILTIN_NORMALIZERS) + [
        ep.name for ep in entry_points(group=_NORMALIZER_ENTRY_GROUP)
    ]
    raise ValueError(f"unknown normalizer {name!r}; available: {', '.join(available) or 'none'}")


def build_pipeline(
    ladder: list[str] | None = None,
    *,
    min_chars_per_page: int = 1,
    min_confidence: float = 0.0,
    engine: str = "ladder",
) -> ExtractionRunner:
    """Build the extraction pipeline from a ladder of normalizer names.

    ``min_confidence`` (0..1) escalates a low-confidence result (e.g. shaky OCR) to
    the next rung; 0.0 (default) never gates on confidence. ``engine`` selects the
    built-in linear ladder (default) or the Haystack engine (ADR 0010) — both walk
    the same rungs and honour the same gate.
    """
    names = ladder or DEFAULT_LADDER
    normalizers = [_build_normalizer(n) for n in names]
    if engine not in ("haystack", "ladder"):
        raise ValueError(f"unknown AFS_PIPELINE_ENGINE {engine!r}; use 'haystack' or 'ladder'")
    if engine == "haystack":
        try:
            from afs_server.extraction.haystack_engine import HaystackExtractionPipeline
        except ModuleNotFoundError:
            # The [haystack] extra isn't installed (e.g. the slim serving image).
            # Fall back to the built-in ladder rather than failing — it walks the
            # same rungs with the same gate. Install afs-server[haystack] for the
            # graph engine (the worker image ships it).
            logger.warning(
                "pipeline_engine=haystack but afs-server[haystack] is not installed; "
                "running the built-in ladder instead"
            )
        else:
            return HaystackExtractionPipeline(
                normalizers, min_chars_per_page=min_chars_per_page, min_confidence=min_confidence
            )
    return ExtractionPipeline(
        normalizers,
        min_chars_per_page=min_chars_per_page,
        min_confidence=min_confidence,
    )


def build_from_settings(settings: Settings) -> ExtractionRunner:
    """The extraction runner the app/worker use: a per-content-type **routed**
    pipeline when ``AFS_PIPELINE_FILE`` is set, else a single ladder/preset. Both
    honour the engine (``AFS_PIPELINE_ENGINE``) and the confidence gate."""
    if settings.pipeline_file:
        from afs_server.extraction.routing import RoutedExtractionPipeline, load_pipeline_file

        config = load_pipeline_file(settings.pipeline_file)
        min_confidence = (
            config.min_confidence
            if config.min_confidence is not None
            else settings.extraction_min_confidence
        )
        return RoutedExtractionPipeline(
            config.routes, engine=settings.pipeline_engine, min_confidence=min_confidence
        )
    return build_pipeline(
        settings.extraction_ladder_names,
        min_confidence=settings.extraction_min_confidence,
        engine=settings.pipeline_engine,
    )


__all__ = [
    "ExtractionOutcome",
    "ExtractionPipeline",
    "ExtractionRunner",
    "build_from_settings",
    "build_pipeline",
    "run_extraction",
]
