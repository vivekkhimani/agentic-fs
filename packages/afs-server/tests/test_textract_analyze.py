"""The textract_analyze rung — AnalyzeDocument → structured markdown, faked client.

The PDF path really rasterizes (pypdfium2 + Pillow); only the API call is faked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction.textract_analyze import (
    TextractAnalyzeNormalizer,
    _features_from_env,
)

_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"


def _analyze_response() -> dict:
    """A small AnalyzeDocument response: body line, a 2x2 table (one of whose
    rows also appears as a LINE — must be de-duped), a key-value form, a figure."""
    return {
        "Blocks": [
            # body words + line
            {"Id": "w1", "BlockType": "WORD", "Text": "Hello"},
            {"Id": "w2", "BlockType": "WORD", "Text": "world"},
            {
                "Id": "L1",
                "BlockType": "LINE",
                "Text": "Hello world",
                "Relationships": [{"Type": "CHILD", "Ids": ["w1", "w2"]}],
            },
            # table words
            {"Id": "h1", "BlockType": "WORD", "Text": "Item"},
            {"Id": "h2", "BlockType": "WORD", "Text": "Qty"},
            {"Id": "r1", "BlockType": "WORD", "Text": "Tank"},
            {"Id": "r2", "BlockType": "WORD", "Text": "1"},
            # a LINE made of table words — should NOT appear in the body stream
            {
                "Id": "L2",
                "BlockType": "LINE",
                "Text": "Item Qty",
                "Relationships": [{"Type": "CHILD", "Ids": ["h1", "h2"]}],
            },
            # table → cells
            {
                "Id": "T1",
                "BlockType": "TABLE",
                "Relationships": [{"Type": "CHILD", "Ids": ["c1", "c2", "c3", "c4"]}],
            },
            {"Id": "c1", "BlockType": "CELL", "RowIndex": 1, "ColumnIndex": 1,
             "Relationships": [{"Type": "CHILD", "Ids": ["h1"]}]},
            {"Id": "c2", "BlockType": "CELL", "RowIndex": 1, "ColumnIndex": 2,
             "Relationships": [{"Type": "CHILD", "Ids": ["h2"]}]},
            {"Id": "c3", "BlockType": "CELL", "RowIndex": 2, "ColumnIndex": 1,
             "Relationships": [{"Type": "CHILD", "Ids": ["r1"]}]},
            {"Id": "c4", "BlockType": "CELL", "RowIndex": 2, "ColumnIndex": 2,
             "Relationships": [{"Type": "CHILD", "Ids": ["r2"]}]},
            # form: Vessel -> Northern Star
            {"Id": "kw", "BlockType": "WORD", "Text": "Vessel"},
            {"Id": "vw1", "BlockType": "WORD", "Text": "Northern"},
            {"Id": "vw2", "BlockType": "WORD", "Text": "Star"},
            {
                "Id": "K1",
                "BlockType": "KEY_VALUE_SET",
                "EntityTypes": ["KEY"],
                "Relationships": [
                    {"Type": "CHILD", "Ids": ["kw"]},
                    {"Type": "VALUE", "Ids": ["V1"]},
                ],
            },
            {
                "Id": "V1",
                "BlockType": "KEY_VALUE_SET",
                "EntityTypes": ["VALUE"],
                "Relationships": [{"Type": "CHILD", "Ids": ["vw1", "vw2"]}],
            },
            {"Id": "F1", "BlockType": "LAYOUT_FIGURE"},
        ]
    }  # fmt: skip


class _FakeTextract:
    def __init__(self) -> None:
        self.calls = 0
        self.features: list[str] | None = None

    def analyze_document(self, Document: dict, FeatureTypes: list[str]) -> dict:  # boto3 shape
        self.calls += 1
        self.features = FeatureTypes
        return _analyze_response()


def _src(name: str, content_type: str | None, path: Path | None = None) -> SourceDocument:
    p = path or Path(name)
    return SourceDocument(filename=p.name, content_type=content_type, size=0, local_path=p)


class TestTextractAnalyzeNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> TextractAnalyzeNormalizer:
        return TextractAnalyzeNormalizer(client=_FakeTextract(), features=["TABLES", "LAYOUT"])

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return _src(_PDF.name, "application/pdf", _PDF)


async def test_renders_table_form_figure_and_dedupes(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "scan.png"
    Image.new("RGB", (12, 12), "white").save(p)
    fake = _FakeTextract()
    rung = TextractAnalyzeNormalizer(client=fake, features=["TABLES", "FORMS", "LAYOUT"])

    result = await rung.normalize(_src("scan.png", "image/png", p))
    md = result.pages[0].markdown

    assert fake.calls == 1
    assert fake.features == ["TABLES", "FORMS", "LAYOUT"]
    # body text present
    assert "Hello world" in md
    # markdown table reconstructed from the cell grid
    assert "| Item | Qty |" in md
    assert "| Tank | 1 |" in md
    # the in-table line ("Item Qty") must not also appear as a loose body line
    assert "Item Qty" not in md.replace("| Item | Qty |", "")
    # form key-value
    assert "**Vessel**: Northern Star" in md
    # figure marker (LAYOUT)
    assert "[figure 1:" in md
    assert result.quality.ocr_used is True


async def test_ocrs_each_pdf_page() -> None:
    fake = _FakeTextract()
    result = await TextractAnalyzeNormalizer(client=fake).normalize(
        _src("s.pdf", "application/pdf", _PDF)
    )
    assert fake.calls == 2  # one AnalyzeDocument call per rasterized page
    assert result.quality.page_count == 2
    assert result.pages[1].source_locator == "ocr:page=2"


def test_routing() -> None:
    n = TextractAnalyzeNormalizer(client=_FakeTextract())
    assert n.accepts(_src("a.pdf", "application/pdf")) is True
    assert n.accepts(_src("a.tiff", None)) is True
    assert n.accepts(_src("a.docx", None)) is False


def test_features_from_env_default_and_drop(monkeypatch) -> None:
    monkeypatch.delenv("AFS_TEXTRACT_FEATURES", raising=False)
    assert _features_from_env() == ["TABLES", "LAYOUT"]
    monkeypatch.setenv("AFS_TEXTRACT_FEATURES", "tables, forms, queries")
    feats = _features_from_env()
    assert feats == ["TABLES", "FORMS"]  # QUERIES dropped (unsupported in v1)
    monkeypatch.setenv("AFS_TEXTRACT_FEATURES", "queries")
    assert _features_from_env() == ["TABLES"]  # fallback — AnalyzeDocument needs ≥1
