"""Shared PDF-page rasterization for OCR rungs (pypdfium2 + Pillow).

OCR engines work on images, so a scanned PDF must be rendered to one image per
page first. pypdfium2 (a base dep) does the rendering; Pillow (each OCR rung's
extra) holds the result. Centralized here so every OCR rung rasterizes
identically.
"""

from __future__ import annotations

from typing import Any


def render_pdf_to_images(path: str, *, scale: float = 2.0) -> list[Any]:
    """Rasterize each PDF page to a PIL image (``scale=2`` ≈ 144 DPI, enough for OCR)."""
    import pypdfium2 as pdfium

    try:
        import PIL.Image  # noqa: F401 - presence check; .to_pil() needs Pillow
    except ModuleNotFoundError as err:  # pragma: no cover - import guard
        raise RuntimeError(
            "rasterizing PDFs for OCR needs Pillow — install the OCR rung's extra"
        ) from err

    pdf = pdfium.PdfDocument(path)
    try:
        images = []
        for index in range(len(pdf)):
            page = pdf[index]
            images.append(page.render(scale=scale).to_pil())
            page.close()
        return images
    finally:
        pdf.close()
