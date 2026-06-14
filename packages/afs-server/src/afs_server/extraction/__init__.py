"""Extraction — the pluggable parser layer.

A `Normalizer` (text_native builtin, or a third-party plugin) is selected by name
into a ladder, exactly like the store registry. Add your own parser: implement
`afs_core.contracts.Normalizer`, certify it with
`afs_core.testing.NormalizerConformance`, register it under the `afs.normalizers`
entry-point group, and name it in the ladder. See `docs/swap-guides/` (extraction).
"""

from __future__ import annotations

from importlib.metadata import entry_points

from afs_core.contracts import Normalizer
from afs_server.extraction.docling import DoclingNormalizer
from afs_server.extraction.docx import DocxNormalizer
from afs_server.extraction.llm import LlmNormalizer
from afs_server.extraction.pdf import PdfNormalizer
from afs_server.extraction.pdftables import PdfTablesNormalizer
from afs_server.extraction.pipeline import ExtractionOutcome, ExtractionPipeline
from afs_server.extraction.rapidocr import RapidOcrNormalizer
from afs_server.extraction.runner import run_extraction
from afs_server.extraction.tesseract import TesseractNormalizer
from afs_server.extraction.text_native import TextNativeNormalizer
from afs_server.extraction.textract import TextractNormalizer
from afs_server.extraction.textract_analyze import TextractAnalyzeNormalizer

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


def build_pipeline(ladder: list[str] | None = None) -> ExtractionPipeline:
    """Build the extraction pipeline from a ladder of normalizer names."""
    names = ladder or DEFAULT_LADDER
    return ExtractionPipeline([_build_normalizer(n) for n in names])


__all__ = ["ExtractionOutcome", "ExtractionPipeline", "build_pipeline", "run_extraction"]
