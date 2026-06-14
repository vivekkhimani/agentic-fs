"""Run the extraction pipeline over one document and write its derived pages.

The single place that turns *bytes → derived/text pages + an ExtractionState*,
shared by the inline ingest path and the async worker (ADR 0009). It owns the
derived-layer writes; the pipeline (a ladder of `Normalizer`s) owns the parsing.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from afs_core import keys
from afs_core.models import ExtractionState, SourceDocument

if TYPE_CHECKING:
    from afs_core.contracts import ObjectStore
    from afs_server.extraction.pipeline import ExtractionPipeline


async def run_extraction(
    objects: ObjectStore,
    pipeline: ExtractionPipeline,
    *,
    tenant_id: str,
    namespace: str,
    entry_id: str,
    path: str,
    data: bytes,
    content_type: str,
) -> ExtractionState:
    """Extract ``data`` and persist its derived pages; return the resulting state.

    A document no rung can read lands ``catalog_only`` — listed and citeable, never
    silently dropped.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        staged = Path(tmpdir) / (path.rsplit("/", 1)[-1] or "doc")
        staged.write_bytes(data)
        outcome = await pipeline.run(
            SourceDocument(
                filename=staged.name,
                content_type=content_type,
                size=len(data),
                local_path=staged,
            )
        )

    if outcome is None:
        return ExtractionState(status="catalog_only", reason="no_extractor")

    all_text = []
    for page in outcome.document.pages:
        await objects.put(
            keys.derived_text_key(tenant_id, namespace, entry_id, page.number),
            page.markdown.encode("utf-8"),
            content_type="text/markdown",
        )
        all_text.append(page.markdown)
    return ExtractionState(
        status="extracted",
        page_count=len(outcome.document.pages),
        extractor=outcome.extractor,
        text_checksum=hashlib.sha256("\n".join(all_text).encode("utf-8")).hexdigest(),
    )
