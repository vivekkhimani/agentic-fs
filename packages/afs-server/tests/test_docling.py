"""The docling rung's routing + registration — the parts that must hold without
the heavy optional dependency installed. Real extraction is certified in
``test_docling_conformance.py`` (skipped unless ``afs-server[docling]`` is in)."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.contracts import NormalizationError
from afs_core.models import SourceDocument
from afs_server.extraction import build_pipeline
from afs_server.extraction.docling import DoclingNormalizer


def _src(name: str, content_type: str | None) -> SourceDocument:
    return SourceDocument(filename=name, content_type=content_type, size=0, local_path=Path(name))


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("report.pdf", "application/pdf"),
        ("memo.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("deck.pptx", None),  # routed by extension when MIME is absent
        ("sheet.xlsx", None),
        ("scan.png", "image/png"),
        ("photo.jpg", None),
    ],
)
def test_accepts_rich_formats(name: str, content_type: str | None) -> None:
    assert DoclingNormalizer().accepts(_src(name, content_type)) is True


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("notes.md", "text/markdown"),  # text_native's job, ahead in the ladder
        ("data.csv", "text/csv"),
        ("a.txt", "text/plain"),
        ("blob.bin", "application/octet-stream"),  # unknown → neither rung → catalog_only
    ],
)
def test_rejects_text_and_unknown(name: str, content_type: str | None) -> None:
    assert DoclingNormalizer().accepts(_src(name, content_type)) is False


def test_docling_builds_without_its_optional_dependency() -> None:
    # The rung is a known builtin and constructs lazily — naming it in the ladder
    # must not import docling (that happens on the first normalize()).
    assert build_pipeline(["text_native", "docling"]) is not None


# --- normalize() logic, exercised with a fake converter (no docling needed) ---
#
# These cover the parts of the rung that are *our* responsibility (page
# iteration, blank-page handling, contiguous renumbering, quality, error
# mapping). The real docling round-trip is certified separately on a PDF fixture.


class _FakeDoc:
    def __init__(self, pages: list[str], full: str = "") -> None:
        self._pages = pages
        self._full = full

    def num_pages(self) -> int:
        return len(self._pages)

    def export_to_markdown(self, page_no: int | None = None) -> str:
        return self._full if page_no is None else self._pages[page_no - 1]


class _FakeResult:
    def __init__(self, document: _FakeDoc, status: str = "SUCCESS") -> None:
        self.document = document
        self.status = type("Status", (), {"name": status})()


class _FakeConverter:
    def __init__(self, result: _FakeResult) -> None:
        self._result = result

    def convert(self, _path: str) -> _FakeResult:
        return self._result


def _with_converter(result: _FakeResult) -> DoclingNormalizer:
    nz = DoclingNormalizer()
    nz._converter = _FakeConverter(result)  # pre-seed so no docling import happens
    return nz


def _pdf(tmp_path: Path) -> SourceDocument:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.3\n")
    return _src(p.name, "application/pdf")


async def test_normalize_emits_one_page_per_source_page(tmp_path: Path) -> None:
    nz = _with_converter(_FakeResult(_FakeDoc(["alpha alpha", "beta beta beta"])))
    result = await nz.normalize(_pdf(tmp_path))
    assert [p.number for p in result.pages] == [1, 2]
    assert [p.source_locator for p in result.pages] == ["page=1", "page=2"]
    assert result.quality.page_count == 2
    assert result.quality.char_count == len("alpha alpha") + len("beta beta beta")
    assert result.quality.min_chars_per_page == len("alpha alpha")


async def test_normalize_drops_blank_pages_but_keeps_numbering_contiguous(
    tmp_path: Path,
) -> None:
    # Page 2 is blank: the read path serves derived pages 1..N with no gaps, so
    # the kept pages renumber to 1,2 while source_locator records the true pages.
    nz = _with_converter(_FakeResult(_FakeDoc(["real one", "   \n ", "real three"])))
    result = await nz.normalize(_pdf(tmp_path))
    assert [p.number for p in result.pages] == [1, 2]
    assert [p.source_locator for p in result.pages] == ["page=1", "page=3"]
    assert result.quality.min_chars_per_page > 0


async def test_normalize_all_blank_is_empty_document(tmp_path: Path) -> None:
    nz = _with_converter(_FakeResult(_FakeDoc(["  ", "\n\t"])))
    with pytest.raises(NormalizationError) as excinfo:
        await nz.normalize(_pdf(tmp_path))
    assert excinfo.value.reason == "empty_document"


async def test_normalize_failure_status_raises(tmp_path: Path) -> None:
    nz = _with_converter(_FakeResult(_FakeDoc(["ignored"]), status="FAILURE"))
    with pytest.raises(NormalizationError) as excinfo:
        await nz.normalize(_pdf(tmp_path))
    assert excinfo.value.reason == "parse_failed"


async def test_normalize_non_paginated_falls_back_to_whole_doc(tmp_path: Path) -> None:
    # Reflowable formats can report zero pages; fall back to the full export.
    nz = _with_converter(_FakeResult(_FakeDoc([], full="whole document text")))
    result = await nz.normalize(_pdf(tmp_path))
    assert len(result.pages) == 1
    assert result.pages[0].markdown == "whole document text"


# --- pre-baked-model converter wiring (no real docling needed) ---


def test_build_converter_without_artifacts_uses_default() -> None:
    from afs_server.extraction.docling import _build_converter

    seen: list[dict] = []

    class _Fake:
        def __init__(self, **kwargs: object) -> None:
            seen.append(kwargs)

    _build_converter(_Fake, None)
    assert seen == [{}]  # plain construction, no format_options


def test_build_converter_degrades_when_offline_api_unavailable() -> None:
    # docling isn't installed here, so the artifacts_path branch can't import the
    # PdfPipelineOptions API → it must fall back to the default converter, not raise.
    from afs_server.extraction.docling import _build_converter

    seen: list[dict] = []

    class _Fake:
        def __init__(self, **kwargs: object) -> None:
            seen.append(kwargs)

    result = _build_converter(_Fake, "/opt/docling/models")
    assert seen == [{}] and result is not None
