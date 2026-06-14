"""Content-type routing (ADR 0010 phase 2) — different document types take
different ladders.

A linear ladder runs every rung for every doc; routing sends each document to a
ladder chosen by its MIME type. So images can skip the text rungs and go straight
to vision/OCR, born-digital PDFs can prefer table-structure rungs, etc. Each route
is itself a normal cascade (built via ``build_pipeline``), so it composes with the
engine choice and the quality gate.

Users configure routes in a small YAML file pointed at by ``AFS_PIPELINE_FILE``:

    # afs-pipeline.yaml
    min_confidence: 0.6
    routes:
      "image/*":          [textract_analyze, llm]
      "application/pdf":   [text_native, pdf, pdftables, textract_analyze, llm]
      "*":                 [text_native, pdf, docx]   # default

Match order is most-specific-first: exact MIME, then ``type/*`` prefix globs, then
the ``*`` default. A document whose type matches no route (and no ``*``) lands
``catalog_only``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from afs_core.models import SourceDocument
    from afs_server.extraction.pipeline import ExtractionOutcome


@dataclass(frozen=True)
class PipelineConfig:
    routes: dict[str, list[str]]
    min_confidence: float | None = None


def load_pipeline_file(path: str) -> PipelineConfig:
    """Parse an ``AFS_PIPELINE_FILE`` routing YAML into a PipelineConfig."""
    try:
        import yaml
    except ModuleNotFoundError as err:  # pragma: no cover - yaml ships with [haystack]
        raise ValueError(
            "AFS_PIPELINE_FILE needs a YAML parser: pip install 'afs-server[haystack]'"
        ) from err

    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    routes = data.get("routes")
    if not isinstance(routes, dict) or not routes:
        raise ValueError(f"{path}: must define a non-empty 'routes' mapping")
    parsed = {str(glob): [str(r) for r in rungs] for glob, rungs in routes.items()}
    min_confidence = data.get("min_confidence")
    return PipelineConfig(routes=parsed, min_confidence=min_confidence)


def select_route(content_type: str | None, routes: dict[str, list[str]]) -> list[str] | None:
    """The ladder for ``content_type``: exact MIME, then ``type/*`` prefix, then ``*``."""
    ct = content_type or ""
    if ct in routes:
        return routes[ct]
    for glob, rungs in routes.items():
        if glob.endswith("/*") and ct.startswith(glob[:-1]):
            return rungs
    return routes.get("*")


class RoutedExtractionPipeline:
    """Routes a document to a per-content-type ladder. Matches the
    ``ExtractionRunner`` protocol (``async run(doc) -> ExtractionOutcome | None``)."""

    def __init__(
        self,
        routes: dict[str, list[str]],
        *,
        engine: str = "haystack",
        min_chars_per_page: int = 1,
        min_confidence: float = 0.0,
    ) -> None:
        from afs_server.extraction import build_pipeline

        # Build each route's cascade once (on the chosen engine).
        self._branches = {
            glob: build_pipeline(
                rungs,
                engine=engine,
                min_chars_per_page=min_chars_per_page,
                min_confidence=min_confidence,
            )
            for glob, rungs in routes.items()
        }
        self._routes = routes

    async def run(self, doc: SourceDocument) -> ExtractionOutcome | None:
        glob = _match_glob(doc.content_type, self._routes)
        branch = self._branches.get(glob)
        if branch is None:
            return None  # no matching route and no "*" default → catalog_only
        return await branch.run(doc)


def _match_glob(content_type: str | None, routes: dict[str, list[str]]) -> str:
    ct = content_type or ""
    if ct in routes:
        return ct
    for glob in routes:
        if glob.endswith("/*") and ct.startswith(glob[:-1]):
            return glob
    return "*"
