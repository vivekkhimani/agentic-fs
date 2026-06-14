"""The ``rapidocr`` rung — lightweight self-hosted OCR (RapidOCR, ONNX).

The "rich but lightweight" sweet spot: PaddleOCR-quality recognition (angle +
detection) on an ONNX runtime — far smaller/faster than torch-based engines, no
GPU, data never leaves. Good when you want better-than-Tesseract OCR self-hosted.
PDFs are rasterized per page (shared `render` helper); images go straight through.

Needs the ``[rapidocr]`` extra (rapidocr-onnxruntime pulls onnxruntime + opencv +
numpy). opencv needs the usual X11/GL system libs at runtime (as the docling
worker image already installs).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport
from afs_server.extraction.render import render_pdf_to_images

if TYPE_CHECKING:
    from afs_core.models import SourceDocument

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


class RapidOcrNormalizer:
    name = "rapidocr"

    def __init__(self, *, ocr: Callable[[Any], str] | None = None) -> None:
        self._ocr = ocr  # callable(PIL image) -> str; injected in tests, else built+cached

    def accepts(self, doc: SourceDocument) -> bool:
        ct = doc.content_type or ""
        if ct.startswith("image/") or ct == "application/pdf":
            return True
        return doc.local_path.suffix.lower() in _IMAGE_EXTS | {".pdf"}

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        return await asyncio.to_thread(self._extract_sync, doc)

    def _extract_sync(self, doc: SourceDocument) -> NormalizedDocument:
        if self._ocr is None:
            self._ocr = _rapidocr_engine()  # load the ONNX models once, then reuse
        is_pdf = (doc.content_type == "application/pdf") or doc.local_path.suffix.lower() == ".pdf"
        if is_pdf:
            images = render_pdf_to_images(str(doc.local_path))
        else:
            from PIL import Image

            images = [Image.open(str(doc.local_path))]

        pages: list[PageText] = []
        for index, image in enumerate(images):
            text = self._ocr(image)
            if not text.strip():
                continue
            pages.append(
                PageText(
                    number=len(pages) + 1, markdown=text, source_locator=f"ocr:page={index + 1}"
                )
            )

        if not pages:
            raise NormalizationError("empty_document", "rapidocr found no text")
        char_counts = [len(p.markdown) for p in pages]
        return NormalizedDocument(
            pages=pages,
            quality=QualityReport(
                page_count=len(pages),
                char_count=sum(char_counts),
                ocr_used=True,
                min_chars_per_page=min(char_counts),
            ),
        )


def _rapidocr_engine() -> Callable[[Any], str]:
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ModuleNotFoundError as err:  # pragma: no cover - import guard
        raise RuntimeError(
            "the rapidocr rung needs the optional extra: pip install 'afs-server[rapidocr]'"
        ) from err

    engine = RapidOCR()

    def ocr(image: Any) -> str:
        result, _elapse = engine(np.array(image))
        # result is a list of [box, text, score]; pull the recognized text in order.
        return "\n".join(line[1] for line in (result or []))

    return ocr
