"""LlamaHub reader → Connector adapter (ADR 0014).

One bridge turns the **300+ LlamaHub community readers** (SharePoint, Confluence,
Notion, Slack, Drive, …) into agentic-fs sources, so we don't hand-write each
connector and contributors reuse a framework they already know.

A LlamaHub reader is a *loader that has already extracted*: it returns
``Document(text, metadata)`` objects, not raw bytes. So this is a **pre-extracted
connector** — ``discover()`` runs the reader and maps each ``Document`` to a
``SourceItem``; ``fetch()`` returns the document's text as ``text/markdown`` bytes.
That flows through the existing ingest path unchanged: the ``text_native`` rung
passes the text straight to derived text, a catalog row appears, and
grep/glob/read just work. Trade-off: we ingest the reader's extracted text, not
the original bytes, so there's no later re-extraction with a richer rung — the
right call for the long tail of sources a reader already covers (our native
local/s3/gdrive connectors stay the path when the original + our ladder matter).

The adapter is **duck-typed**: it needs only an object with
``load_data() -> list[doc]`` where each ``doc`` has ``.text`` (or ``.get_content()``)
and ``.metadata``. It imports nothing from llama-index itself, so the registry and
other connectors don't pay for it; install a reader with the ``[llamahub]`` extra
plus the per-source ``llama-index-readers-*`` package.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from collections.abc import Iterator
from typing import Any

from afs_core.models import SourceItem


def _doc_text(doc: Any) -> str:
    text = getattr(doc, "text", None)
    if text is None and hasattr(doc, "get_content"):
        text = doc.get_content()
    return text or ""


def _doc_path(doc: Any, index: int) -> str:
    """A clean relative POSIX path for one document, from its metadata."""
    meta = getattr(doc, "metadata", None) or {}
    raw = next(
        (
            meta[k]
            for k in ("file_path", "file_name", "filename", "source", "url", "title")
            if meta.get(k)
        ),
        None,
    )
    if not raw:
        return f"doc-{index}.md"
    raw = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", str(raw))  # strip a URL scheme
    parts = [p for p in raw.replace("\\", "/").split("/") if p and p != ".."]
    return "/".join(parts) or f"doc-{index}.md"


def _doc_version(doc: Any, text: str) -> str:
    meta = getattr(doc, "metadata", None) or {}
    for key in ("version", "revision", "modified_time", "last_modified", "mtime", "etag"):
        if meta.get(key):
            return f"{key}:{meta[key]}"
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_reader(source: str, options: dict[str, str]) -> Any:
    """Import + construct a reader from a dotted class path (the CLI/registry path).

    ``source`` is e.g. ``llama_index.readers.google.GoogleDriveReader``; options are
    passed as keyword args to its constructor (they arrive as strings from the CLI,
    so a reader needing typed args is better constructed programmatically with
    ``reader=``).
    """
    if not source:
        raise ValueError(
            "the llamahub connector needs a reader class path as `source` "
            "(e.g. llama_index.readers.notion.NotionPageReader), or a reader= instance"
        )
    module_path, _, cls_name = source.rpartition(".")
    if not module_path:
        raise ValueError(f"invalid reader path {source!r}; expected module.ClassName")
    cls = getattr(importlib.import_module(module_path), cls_name)
    return cls(**options)


class LlamaHubConnector:
    """Adapts any LlamaHub/LlamaIndex reader to the ``Connector`` contract."""

    name = "llamahub"

    def __init__(self, source: str = "", *, reader: Any = None, **options: str) -> None:
        # `reader` is injected programmatically (and in tests); otherwise the
        # reader is built from the dotted `source` path + options.
        self._reader = reader if reader is not None else _load_reader(source, options)
        self._docs: list[Any] | None = None

    def _documents(self) -> list[Any]:
        # Cached so discover() is repeatable (the engine may enumerate twice) and
        # the reader's (often expensive) load runs once.
        if self._docs is None:
            self._docs = list(self._reader.load_data())
        return self._docs

    def discover(self) -> Iterator[SourceItem]:
        seen: set[str] = set()
        for index, doc in enumerate(self._documents()):
            text = _doc_text(doc)
            path = _doc_path(doc, index)
            if path in seen:  # keep paths unique within the source
                stem, dot, ext = path.rpartition(".")
                path = f"{stem}-{index}.{ext}" if dot else f"{path}-{index}"
            seen.add(path)
            yield SourceItem(
                path=path,
                locator=str(index),
                size=len(text.encode("utf-8")),
                content_type="text/markdown",  # text; the text_native rung passes it through
                version=_doc_version(doc, text),
            )

    def fetch(self, item: SourceItem) -> bytes:
        return _doc_text(self._documents()[int(item.locator)]).encode("utf-8")
