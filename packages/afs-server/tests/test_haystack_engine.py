"""The Haystack pipeline engine (ADR 0010) — must match the built-in ladder's
cascade behavior. Uses fake rungs + the real sample.pdf for an engine-equivalence
check; the [haystack] extra is in the dev group so this runs in CI."""

from __future__ import annotations

from pathlib import Path

from afs_core.models import NormalizedDocument, PageText, QualityReport, SourceDocument
from afs_server.extraction import build_pipeline
from afs_server.extraction.haystack_engine import HaystackExtractionPipeline

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


class _Rung:
    """Accepts everything; returns `chars`/`confidence` or declines (no pages)."""

    def __init__(self, name: str, *, chars: int = 9, confidence: float | None = None) -> None:
        self.name = name
        self._chars = chars
        self._confidence = confidence

    def accepts(self, doc: SourceDocument) -> bool:
        return True

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        return NormalizedDocument(
            pages=[PageText(number=1, markdown="x" * self._chars)],
            quality=QualityReport(
                page_count=1,
                char_count=self._chars,
                min_chars_per_page=self._chars,
                confidence=self._confidence,
            ),
        )


_ANY = SourceDocument(filename="x", content_type=None, size=0, local_path=Path("x"))


async def test_first_above_gate_rung_wins() -> None:
    pipe = HaystackExtractionPipeline([_Rung("a"), _Rung("b")])
    outcome = await pipe.run(_ANY)
    assert outcome is not None and outcome.extractor == "a"


async def test_escalates_past_below_gate_rung() -> None:
    # first rung is below the char gate (0 chars) → fall through to the second.
    pipe = HaystackExtractionPipeline([_Rung("a", chars=0), _Rung("b", chars=5)])
    outcome = await pipe.run(_ANY)
    assert outcome is not None and outcome.extractor == "b"


async def test_no_rung_passes_is_catalog_only() -> None:
    pipe = HaystackExtractionPipeline([_Rung("a", chars=0), _Rung("b", chars=0)])
    assert await pipe.run(_ANY) is None


async def test_confidence_gate_escalates() -> None:
    pipe = HaystackExtractionPipeline(
        [_Rung("ocr", confidence=0.5), _Rung("llm", confidence=0.95)], min_confidence=0.6
    )
    outcome = await pipe.run(_ANY)
    assert outcome is not None and outcome.extractor == "llm"


async def test_empty_ladder_is_catalog_only() -> None:
    assert await HaystackExtractionPipeline([]).run(_ANY) is None


async def test_matches_ladder_on_real_document(tmp_path: Path) -> None:
    """The two engines must agree on a real doc end-to-end (default ladder)."""
    md = tmp_path / "note.md"
    md.write_text("# Title\n\nbody text")
    doc = SourceDocument(
        filename="note.md", content_type="text/markdown", size=md.stat().st_size, local_path=md
    )

    ladder = build_pipeline(["text_native", "pdf", "docx"], engine="ladder")
    haystack = build_pipeline(["text_native", "pdf", "docx"], engine="haystack")
    a = await ladder.run(doc)
    b = await haystack.run(doc)
    assert a is not None and b is not None
    assert a.extractor == b.extractor == "text_native"
    assert a.document.pages[0].markdown == b.document.pages[0].markdown


async def test_matches_ladder_on_born_digital_pdf() -> None:
    doc = SourceDocument(
        filename="sample.pdf",
        content_type="application/pdf",
        size=_PDF.stat().st_size,
        local_path=_PDF,
    )
    ladder = await build_pipeline(["text_native", "pdf", "docx"], engine="ladder").run(doc)
    haystack = await build_pipeline(["text_native", "pdf", "docx"], engine="haystack").run(doc)
    assert ladder is not None and haystack is not None
    assert ladder.extractor == haystack.extractor == "pdf"
    assert ladder.document.quality.page_count == haystack.document.quality.page_count


def test_unknown_engine_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown AFS_PIPELINE_ENGINE"):
        build_pipeline(["text_native"], engine="nope")
