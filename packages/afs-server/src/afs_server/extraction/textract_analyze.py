"""The ``textract_analyze`` rung — Textract **AnalyzeDocument** for structure.

The cheap ``textract`` rung (``DetectDocumentText``) flattens tables to a line
stream. This rung uses ``AnalyzeDocument`` to **preserve structure**: real
markdown tables (from the cell grid), key-value **forms**, and **figure markers**
(LAYOUT locates figures — Textract never describes them; that's the ``llm`` rung's
job). Pricier than the cheap rung, so it's its own ladder entry — see ADR 0010.

Features are configurable via ``AFS_TEXTRACT_FEATURES`` (default ``TABLES,LAYOUT``;
``FORMS`` adds key-value extraction at higher cost). PDFs are rasterized per page
(pypdfium2 + Pillow, shared with the ``textract`` rung); images go straight through.
boto3 is a base dep; the PDF path needs Pillow — the ``[textract]`` extra. The
worker's IAM must allow ``textract:AnalyzeDocument``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport
from afs_server.extraction.textract import _render_pdf_to_pngs

if TYPE_CHECKING:
    from afs_core.models import SourceDocument

logger = logging.getLogger("afs_server.extraction.textract_analyze")

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
# AnalyzeDocument FeatureTypes we render to markdown. QUERIES/SIGNATURES need
# extra request config and are a separate follow-up; unknown values are dropped.
_SUPPORTED_FEATURES = ("TABLES", "FORMS", "LAYOUT")


def _features_from_env() -> list[str]:
    raw = os.environ.get("AFS_TEXTRACT_FEATURES", "TABLES,LAYOUT")
    requested = [f.strip().upper() for f in raw.split(",") if f.strip()]
    features = [f for f in requested if f in _SUPPORTED_FEATURES]
    dropped = [f for f in requested if f not in _SUPPORTED_FEATURES]
    if dropped:
        logger.warning(
            "ignoring unsupported AFS_TEXTRACT_FEATURES %s (supported: %s)",
            ",".join(dropped),
            ",".join(_SUPPORTED_FEATURES),
        )
    return features or ["TABLES"]  # AnalyzeDocument requires ≥1 feature


class TextractAnalyzeNormalizer:
    name = "textract_analyze"

    def __init__(
        self,
        *,
        region: str | None = None,
        client: Any = None,
        features: list[str] | None = None,
    ) -> None:
        self._region = region
        self._client = client  # injected in tests; built lazily otherwise
        self._features = features or _features_from_env()

    def accepts(self, doc: SourceDocument) -> bool:
        ct = doc.content_type or ""
        if ct.startswith("image/") or ct == "application/pdf":
            return True
        return doc.local_path.suffix.lower() in _IMAGE_EXTS | {".pdf"}

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        return await asyncio.to_thread(self._extract_sync, doc)

    def _extract_sync(self, doc: SourceDocument) -> NormalizedDocument:
        is_pdf = (doc.content_type == "application/pdf") or doc.local_path.suffix.lower() == ".pdf"
        page_images = (
            _render_pdf_to_pngs(str(doc.local_path)) if is_pdf else [doc.local_path.read_bytes()]
        )

        pages: list[PageText] = []
        confidences: list[float] = []
        for index, image in enumerate(page_images):
            blocks = self._analyze(image).get("Blocks", [])
            markdown = _analyze_to_markdown(blocks)
            if not markdown.strip():
                continue  # blank page; keep numbering contiguous
            page_confidence = _mean_line_confidence(blocks)
            if page_confidence is not None:
                confidences.append(page_confidence)
            pages.append(
                PageText(
                    number=len(pages) + 1,
                    markdown=markdown,
                    source_locator=f"ocr:page={index + 1}",
                )
            )

        if not pages:
            raise NormalizationError("empty_document", "textract analyze found no content")
        char_counts = [len(p.markdown) for p in pages]
        return NormalizedDocument(
            pages=pages,
            quality=QualityReport(
                page_count=len(pages),
                char_count=sum(char_counts),
                ocr_used=True,
                min_chars_per_page=min(char_counts),
                confidence=min(confidences) if confidences else None,
            ),
        )

    def _analyze(self, image_bytes: bytes) -> dict:
        return self._textract().analyze_document(
            Document={"Bytes": image_bytes}, FeatureTypes=self._features
        )

    def _textract(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("textract", region_name=self._region)
        return self._client


def _mean_line_confidence(blocks: list[dict]) -> float | None:
    """Mean LINE-block confidence in [0, 1], or None if Textract reported none."""
    scores = [b["Confidence"] for b in blocks if b.get("BlockType") == "LINE" and "Confidence" in b]
    return (sum(scores) / len(scores) / 100.0) if scores else None


def _analyze_to_markdown(blocks: list[dict]) -> str:
    """Render an AnalyzeDocument block list to markdown: body text + tables + forms
    + figure markers. Table-cell text is removed from the body stream so it isn't
    duplicated alongside the rendered table."""
    by_id = {b["Id"]: b for b in blocks if "Id" in b}

    def child_text(block: dict) -> str:
        words: list[str] = []
        for rel in block.get("Relationships", []):
            if rel.get("Type") != "CHILD":
                continue
            for cid in rel.get("Ids", []):
                child = by_id.get(cid, {})
                if child.get("BlockType") == "WORD":
                    words.append(child.get("Text", ""))
                elif (
                    child.get("BlockType") == "SELECTION_ELEMENT"
                    and child.get("SelectionStatus") == "SELECTED"
                ):
                    words.append("[x]")
        return " ".join(w for w in words if w)

    def child_word_ids(block: dict) -> set[str]:
        ids: set[str] = set()
        for rel in block.get("Relationships", []):
            if rel.get("Type") == "CHILD":
                ids.update(rel.get("Ids", []))
        return ids

    # --- tables → markdown, recording which words they consume ---
    tables_md: list[str] = []
    table_word_ids: set[str] = set()
    for block in blocks:
        if block.get("BlockType") != "TABLE":
            continue
        cells = [
            by_id[cid]
            for cid in child_word_ids(block)
            if by_id.get(cid, {}).get("BlockType") == "CELL"
        ]
        if not cells:
            continue
        nrows = max(c["RowIndex"] for c in cells)
        ncols = max(c["ColumnIndex"] for c in cells)
        grid = [["" for _ in range(ncols)] for _ in range(nrows)]
        for cell in cells:
            grid[cell["RowIndex"] - 1][cell["ColumnIndex"] - 1] = child_text(cell)
            table_word_ids.update(child_word_ids(cell))
        rendered = _grid_to_markdown(grid)
        if rendered:
            tables_md.append(rendered)

    # --- forms (KEY_VALUE_SET) → key: value ---
    forms: list[str] = []
    for block in blocks:
        if block.get("BlockType") != "KEY_VALUE_SET" or "KEY" not in block.get("EntityTypes", []):
            continue
        key = child_text(block)
        value = ""
        for rel in block.get("Relationships", []):
            if rel.get("Type") == "VALUE":
                for vid in rel.get("Ids", []):
                    value = child_text(by_id.get(vid, {})) or value
        if key:
            forms.append(f"**{key}**: {value}".rstrip())

    # --- body text from LINE blocks not wholly inside a table ---
    body: list[str] = []
    figures = 0
    for block in blocks:
        bt = block.get("BlockType")
        if bt == "LINE":
            line_ids = child_word_ids(block)
            if line_ids and line_ids <= table_word_ids:
                continue  # this line is a table's cells — rendered in the table instead
            text = block.get("Text") or child_text(block)
            if text.strip():
                body.append(text)
        elif bt == "LAYOUT_FIGURE":
            figures += 1

    sections: list[str] = []
    if body:
        sections.append("\n".join(body))
    sections.extend(tables_md)
    if forms:
        sections.append("\n".join(forms))
    sections.extend(f"[figure {i + 1}: see source page]" for i in range(figures))
    return "\n\n".join(s for s in sections if s.strip())


def _grid_to_markdown(grid: list[list[str]]) -> str:
    if not grid or not grid[0]:
        return ""
    width = max(len(row) for row in grid)

    def cell(value: str) -> str:
        return value.replace("\n", " ").replace("|", "\\|").strip()

    norm = [[cell(row[i] if i < len(row) else "") for i in range(width)] for row in grid]
    header, *rest = norm
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rest)
    return "\n".join(lines)
