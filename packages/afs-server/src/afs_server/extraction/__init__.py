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
from afs_server.extraction.pipeline import ExtractionOutcome, ExtractionPipeline
from afs_server.extraction.runner import run_extraction
from afs_server.extraction.text_native import TextNativeNormalizer

_NORMALIZER_ENTRY_GROUP = "afs.normalizers"

# Builtin normalizers: name -> factory. `docling` is constructed only when named
# in the ladder, and only then needs its optional dependency.
_BUILTIN_NORMALIZERS = {
    "text_native": TextNativeNormalizer,
    "docling": DoclingNormalizer,
}

# Default ladder (config, not code). Just `text_native` so the base install pulls
# no heavy deps; opt into richer rungs via AFS_EXTRACTION_LADDER (e.g.
# "text_native,docling") once that rung's extra is installed.
DEFAULT_LADDER = ["text_native"]


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
