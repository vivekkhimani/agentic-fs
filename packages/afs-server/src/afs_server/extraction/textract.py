"""The ``textract`` rung — AWS Textract OCR for scanned PDFs and images.

Managed OCR (no local ML): strong on real-world scans, forms, tables, and
handwriting — the cases where docling is weak. PDFs are rasterized per page
(pypdfium2 + Pillow) and each page sent to Textract's synchronous
``detect_document_text``; image files go straight through.

boto3 is a base dep; the **PDF** path also needs Pillow — the `[textract]` extra.
In the ladder, the lightweight `pdf` rung handles text-layer PDFs first, so this
only runs on the scans it leaves empty.
"""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING, Any

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport

if TYPE_CHECKING:
    from afs_core.models import SourceDocument

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


class TextractNormalizer:
    name = "textract"

    def __init__(self, *, region: str | None = None, client: Any = None) -> None:
        self._region = region
        self._client = client  # injected in tests; built lazily otherwise

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
            text, confidence = self._ocr(image)
            if not text.strip():
                continue  # blank page; keep numbering contiguous
            if confidence is not None:
                confidences.append(confidence)
            pages.append(
                PageText(
                    number=len(pages) + 1,
                    markdown=text,
                    source_locator=f"ocr:page={index + 1}",
                )
            )

        if not pages:
            raise NormalizationError("empty_document", "textract found no text")
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

    def _ocr(self, image_bytes: bytes) -> tuple[str, float | None]:
        resp = self._textract().detect_document_text(Document={"Bytes": image_bytes})
        lines = [b for b in resp.get("Blocks", []) if b.get("BlockType") == "LINE"]
        text = "\n".join(b.get("Text", "") for b in lines)
        scores = [b["Confidence"] for b in lines if "Confidence" in b]
        confidence = (sum(scores) / len(scores) / 100.0) if scores else None
        return text, confidence

    def _textract(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("textract", region_name=self._region)
        return self._client


def _render_pdf_to_pngs(path: str) -> list[bytes]:
    """Rasterize each PDF page to PNG bytes for OCR (pypdfium2 render → Pillow)."""
    import pypdfium2 as pdfium

    try:
        import PIL.Image  # noqa: F401 - presence check; render().to_pil() needs Pillow
    except ModuleNotFoundError as err:  # pragma: no cover - import guard
        raise RuntimeError(
            "the textract rung needs Pillow to OCR PDFs: pip install 'afs-server[textract]'"
        ) from err

    pdf = pdfium.PdfDocument(path)
    try:
        out: list[bytes] = []
        for index in range(len(pdf)):
            page = pdf[index]
            pil_image = page.render(scale=2).to_pil()  # ~144 DPI, enough for OCR
            page.close()
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            out.append(buffer.getvalue())
        return out
    finally:
        pdf.close()
