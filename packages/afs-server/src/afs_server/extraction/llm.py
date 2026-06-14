"""The ``llm`` rung — batteries-included multimodal extraction (ADR 0010).

Sends each page image to a vision LLM (Anthropic Claude or OpenAI) and asks for
clean markdown that **preserves tables and describes figures/diagrams inline**.
It's the most capable and most expensive rung: it handles the cases the others
can't — scanned *and* born-digital, complex layout, and — uniquely — **diagrams**
(which Textract only locates, never describes). Opt-in via the ladder.

**Per-page, not whole-PDF.** We rasterize each page (pypdfium2 + Pillow, shared
with the OCR rungs) and send one vision call per page. This maps 1:1 to our
derived-page / citation model (``llm:page=N``), is provider-uniform (image input),
and sidesteps the providers' whole-document limits (Claude 100 pp/32 MB, OpenAI
50 MB) so a 300-page booklet just works. The trade-off is no cross-page context
and one call per page — that's the cost of "max fidelity," and it's opt-in.

Pick a provider with ``AFS_LLM_PROVIDER`` (``anthropic`` default | ``openai``) and
``AFS_LLM_MODEL``; the rung lazy-imports the selected SDK (the ``[anthropic]`` /
``[openai]`` extra) and reads its standard API-key env var.
"""

from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from afs_core.contracts import NormalizationError
from afs_core.models import NormalizedDocument, PageText, QualityReport
from afs_server.extraction.textract import _render_pdf_to_pngs

if TYPE_CHECKING:
    from afs_core.models import SourceDocument

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

_DEFAULT_MODELS = {"anthropic": "claude-sonnet-4-6", "openai": "gpt-4o"}

_PROMPT = (
    "Transcribe this document page into clean GitHub-flavored Markdown. "
    "Preserve tables as Markdown tables and keep the original reading order. "
    "Describe any figure, diagram, chart, photo, or technical drawing inline as "
    "'[Figure: <concise description of what it shows>]'. "
    "Do not add commentary or any text that is not on the page. "
    "Output only the Markdown."
)

# Page-image transcriber: PNG bytes -> markdown. Injected in tests; built lazily
# from the configured provider otherwise.
Transcriber = Callable[[bytes], str]


class LlmNormalizer:
    name = "llm"

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 8192,
        transcribe: Transcriber | None = None,
    ) -> None:
        self._provider = (provider or os.environ.get("AFS_LLM_PROVIDER", "anthropic")).lower()
        self._model = (
            model or os.environ.get("AFS_LLM_MODEL") or _DEFAULT_MODELS.get(self._provider)
        )
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._transcribe = transcribe  # injected in tests

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

        transcribe = self._transcriber()
        pages: list[PageText] = []
        for index, image in enumerate(page_images):
            markdown = transcribe(image)
            if not markdown.strip():
                continue  # blank page; keep numbering contiguous
            pages.append(
                PageText(
                    number=len(pages) + 1,
                    markdown=markdown.strip(),
                    source_locator=f"llm:page={index + 1}",
                )
            )

        if not pages:
            raise NormalizationError("empty_document", "the llm rung produced no text")
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

    def _transcriber(self) -> Transcriber:
        if self._transcribe is None:
            if not self._model:
                raise NormalizationError(
                    "llm_misconfigured", f"no model for provider {self._provider!r}"
                )
            self._transcribe = _build_transcriber(
                self._provider, self._model, self._api_key, self._max_tokens
            )
        return self._transcribe


def _build_transcriber(
    provider: str, model: str, api_key: str | None, max_tokens: int
) -> Transcriber:
    if provider == "anthropic":
        return _anthropic_transcriber(model, api_key, max_tokens)
    if provider == "openai":
        return _openai_transcriber(model, api_key, max_tokens)
    raise NormalizationError("llm_misconfigured", f"unknown AFS_LLM_PROVIDER {provider!r}")


def _anthropic_transcriber(model: str, api_key: str | None, max_tokens: int) -> Transcriber:
    try:
        import anthropic
    except ModuleNotFoundError as err:  # rung named but extra not installed → decline
        raise NormalizationError("missing_dependency", "install afs-server[anthropic]") from err

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def transcribe(png: bytes) -> str:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": base64.standard_b64encode(png).decode(),
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
        return "".join(b.text for b in message.content if getattr(b, "type", None) == "text")

    return transcribe


def _openai_transcriber(model: str, api_key: str | None, max_tokens: int) -> Transcriber:
    try:
        import openai
    except ModuleNotFoundError as err:  # rung named but extra not installed → decline
        raise NormalizationError("missing_dependency", "install afs-server[openai]") from err

    client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()

    def transcribe(png: bytes) -> str:
        b64 = base64.standard_b64encode(png).decode()
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
        )
        return resp.choices[0].message.content or ""

    return transcribe
