"""The Haystack pipeline engine (ADR 0010).

An alternative to the built-in linear ``ExtractionPipeline``: the same ladder of
``Normalizer`` rungs, but wired as a Haystack ``AsyncPipeline`` so pipelines can
grow branches (content-type routers) and become user-configurable (YAML) without
us hand-rolling a graph engine. Opt in with ``AFS_PIPELINE_ENGINE=haystack``
(needs the ``[haystack]`` extra); the default stays the built-in ladder.

The cascade is expressed as a real graph: each rung is a component that emits
**either** a winning ``outcome`` **or** the document on ``next_doc`` (forwarded to
the next rung). Every rung's ``outcome`` converges on a variadic collector that
returns the first — so behavior matches the built-in ladder exactly. This module
imports ``haystack`` at top level, so it's only imported when the engine is
selected (and the extra installed).
"""

import asyncio
import os

# Haystack phones home by default; turn it off before importing the package.
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")

# NOTE: no `from __future__ import annotations` here — Haystack introspects the
# run/run_async signatures at runtime to build its sockets, and stringified
# annotations would hide the `Variadic[...]` marker. So all annotation types are
# imported at runtime, not under TYPE_CHECKING.
from haystack import AsyncPipeline, component
from haystack.core.component.types import Variadic

from afs_core.contracts import NormalizationError, Normalizer
from afs_core.models import SourceDocument
from afs_server.extraction.pipeline import ExtractionOutcome, passes_gate


@component
class NormalizerComponent:
    """Wraps a ``Normalizer`` rung. Emits ``outcome`` when it accepts the document
    and clears the gate; otherwise emits ``next_doc`` to fall through to the next."""

    def __init__(
        self, normalizer: Normalizer, *, min_chars_per_page: int, min_confidence: float
    ) -> None:
        self._nz = normalizer
        self._min_chars = min_chars_per_page
        self._min_confidence = min_confidence

    @component.output_types(outcome=ExtractionOutcome, next_doc=SourceDocument)
    def run(self, doc: SourceDocument) -> dict:
        # Async-only at runtime (AsyncPipeline calls run_async); this exists for the
        # required sync entrypoint + output-socket parity.
        return asyncio.run(self.run_async(doc))

    @component.output_types(outcome=ExtractionOutcome, next_doc=SourceDocument)
    async def run_async(self, doc: SourceDocument) -> dict:
        if not self._nz.accepts(doc):
            return {"next_doc": doc}
        try:
            result = await self._nz.normalize(doc)
        except NormalizationError:
            return {"next_doc": doc}
        if result.pages and passes_gate(result.quality, self._min_chars, self._min_confidence):
            return {"outcome": ExtractionOutcome(document=result, extractor=self._nz.name)}
        return {"next_doc": doc}


@component
class _OutcomeCollector:
    """Returns the first winning outcome (only one rung ever emits one)."""

    @component.output_types(outcome=ExtractionOutcome)
    def run(self, outcomes: Variadic[ExtractionOutcome]) -> dict:
        chosen = next(iter(outcomes), None)
        return {"outcome": chosen} if chosen is not None else {}


class HaystackExtractionPipeline:
    """Built-in-ladder-equivalent cascade as a Haystack ``AsyncPipeline``. Matches
    the ``ExtractionRunner`` protocol (``async run(doc) -> ExtractionOutcome | None``)."""

    def __init__(
        self,
        normalizers: list[Normalizer],
        *,
        min_chars_per_page: int = 1,
        min_confidence: float = 0.0,
    ) -> None:
        pipe = AsyncPipeline()
        names: list[str] = []
        for index, nz in enumerate(normalizers):
            name = f"rung_{index}"
            pipe.add_component(
                name,
                NormalizerComponent(
                    nz, min_chars_per_page=min_chars_per_page, min_confidence=min_confidence
                ),
            )
            names.append(name)
        pipe.add_component("collector", _OutcomeCollector())
        for index, name in enumerate(names):
            pipe.connect(f"{name}.outcome", "collector.outcomes")
            if index + 1 < len(names):
                pipe.connect(f"{name}.next_doc", f"{names[index + 1]}.doc")

        self._pipe = pipe
        self._first = names[0] if names else None

    async def run(self, doc: SourceDocument) -> ExtractionOutcome | None:
        if self._first is None:
            return None
        result = await self._pipe.run_async({self._first: {"doc": doc}})
        return result.get("collector", {}).get("outcome")
