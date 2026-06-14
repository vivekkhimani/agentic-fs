"""The ``tesseract`` rung — lightweight self-hosted OCR (Tesseract via pytesseract).

The cheapest OCR option: a CPU binary, no ML runtime. Good on clean printed
scans; weaker on degraded scans / tables / handwriting (use ``textract`` or a DL
engine for those). Needs the ``[tesseract]`` extra **and** the tesseract system
binary installed (e.g. `dnf install tesseract`). In the ladder the lightweight
`pdf` rung handles text-layer PDFs first, so this only OCRs the scans it leaves
empty.
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


class TesseractNormalizer:
    name = "tesseract"

    def __init__(self, *, lang: str = "eng", ocr: Callable[[Any], str] | None = None) -> None:
        self._lang = lang
        self._ocr = ocr  # callable(PIL image) -> str; injected in tests

    def accepts(self, doc: SourceDocument) -> bool:
        ct = doc.content_type or ""
        if ct.startswith("image/") or ct == "application/pdf":
            return True
        return doc.local_path.suffix.lower() in _IMAGE_EXTS | {".pdf"}

    async def normalize(self, doc: SourceDocument) -> NormalizedDocument:
        return await asyncio.to_thread(self._extract_sync, doc)

    def _extract_sync(self, doc: SourceDocument) -> NormalizedDocument:
        ocr = self._ocr or _pytesseract_ocr(self._lang)
        is_pdf = (doc.content_type == "application/pdf") or doc.local_path.suffix.lower() == ".pdf"
        if is_pdf:
            images = render_pdf_to_images(str(doc.local_path))
        else:
            from PIL import Image

            images = [Image.open(str(doc.local_path))]

        pages: list[PageText] = []
        for index, image in enumerate(images):
            text = ocr(image)
            if not text.strip():
                continue
            pages.append(
                PageText(
                    number=len(pages) + 1, markdown=text, source_locator=f"ocr:page={index + 1}"
                )
            )

        if not pages:
            raise NormalizationError("empty_document", "tesseract found no text")
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


def _pytesseract_ocr(lang: str) -> Callable[[Any], str]:
    try:
        import pytesseract
    except ModuleNotFoundError as err:  # pragma: no cover - import guard
        raise RuntimeError(
            "the tesseract rung needs the optional extra (pip install 'afs-server[tesseract]') "
            "and the tesseract system binary"
        ) from err

    def ocr(image: Any) -> str:
        return pytesseract.image_to_string(image, lang=lang)

    return ocr
