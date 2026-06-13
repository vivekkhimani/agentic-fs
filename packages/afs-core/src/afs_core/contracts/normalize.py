"""The ``Normalizer`` contract (plan §5.4) — the extractor/parser seam.

A normalizer turns one raw document into normalized per-page markdown. It is the
*only* place document parsing lives: text_native, docling, llamaparse, and any
custom parser are all just `Normalizer`s. The `ExtractionPipeline` (in
afs-server) orders them into a ladder, applies a quality gate, and degrades to
`catalog_only` — none of which a normalizer needs to know about.

Adding your own: implement this Protocol, certify it against
`afs_core.testing.NormalizerConformance`, register it via the `afs.normalizers`
entry-point group, and name it in the extraction ladder. No core changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from afs_core.models import NormalizedDocument, SourceDocument


class NormalizationError(Exception):
    """A normalizer couldn't parse the document. Carries a closed-vocabulary
    ``reason`` (events v1) so the pipeline can record why and try the next rung."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


@runtime_checkable
class Normalizer(Protocol):
    name: str

    def accepts(self, doc: SourceDocument) -> bool:
        """Whether this normalizer claims the document (by MIME/extension)."""
        ...

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        """Parse ``doc`` into per-page markdown, or raise ``NormalizationError``."""
        ...
