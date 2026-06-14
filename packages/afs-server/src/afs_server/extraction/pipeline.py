"""The extraction pipeline — orders normalizers into a ladder, gates on quality,
and degrades to catalog_only (plan §5.4, §9.2).

This is the boundary the maintainer's feedback identified: parsers (`Normalizer`s)
produce a `NormalizedDocument`; the pipeline decides which rung wins and whether
the result is good enough — neither knows about S3 keys or catalog rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from afs_core.contracts import NormalizationError

if TYPE_CHECKING:
    from afs_core.contracts import Normalizer
    from afs_core.models import NormalizedDocument, QualityReport, SourceDocument

logger = logging.getLogger("afs_server.extraction")


@dataclass(frozen=True)
class ExtractionOutcome:
    document: NormalizedDocument
    extractor: str  # which rung produced it (recorded on the catalog row)


class ExtractionRunner(Protocol):
    """What ``build_pipeline`` returns — the ladder or the Haystack engine. Both
    walk rungs and return the winning outcome (or ``None`` ⇒ catalog_only)."""

    async def run(self, doc: SourceDocument) -> ExtractionOutcome | None: ...


def passes_gate(quality: QualityReport, min_chars: int, min_confidence: float) -> bool:
    """The shared quality gate (used by both pipeline engines): enough text, and —
    when a rung reports it — confidence at or above the threshold."""
    if quality.min_chars_per_page < min_chars:
        return False
    return quality.confidence is None or quality.confidence >= min_confidence


class ExtractionPipeline:
    """Walks the ladder in order; the first rung that accepts the document and
    produces an above-quality-gate result wins. Returns ``None`` ⇒ catalog_only."""

    def __init__(
        self,
        ladder: list[Normalizer],
        *,
        min_chars_per_page: int = 1,
        min_confidence: float = 0.0,
    ) -> None:
        self._ladder = ladder
        self._min_chars = min_chars_per_page
        self._min_confidence = min_confidence

    async def run(self, doc: SourceDocument) -> ExtractionOutcome | None:
        for nz in self._ladder:
            if not nz.accepts(doc):
                continue
            try:
                result = await nz.normalize(doc)
            except NormalizationError as err:
                logger.info("normalizer %s declined %s: %s", nz.name, doc.filename, err.reason)
                continue
            if result.pages and passes_gate(result.quality, self._min_chars, self._min_confidence):
                return ExtractionOutcome(document=result, extractor=nz.name)
            # below the quality gate — fall through to the next (escalation) rung.
            logger.info(
                "normalizer %s below gate for %s (min_chars=%s, confidence=%s)",
                nz.name,
                doc.filename,
                result.quality.min_chars_per_page,
                result.quality.confidence,
            )
        return None
