"""Tier-2 power tools: read-by-section, fs_tables, fs_diff (ADR 0012)."""

from __future__ import annotations

import pytest

from afs_core import keys
from afs_core.errors import CatalogOnlyError, ValidationError
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.auth import resolve_dev_context
from afs_server.services import FsService
from afs_server.settings import Settings

P1 = "# Intro\n\nwelcome\n\n## Setup\ninstall steps here"
P2 = "## Security\n\nencrypt at rest\n\n## Appendix\nrefs"


def _ctx():
    return resolve_dev_context(Settings())


async def _seed() -> FsService:
    cat, obj = InMemoryCatalogStore(), InMemoryObjectStore()

    async def doc(path, eid, pages_text, *, status="extracted", ct="text/markdown"):
        n = len(pages_text)
        await cat.put_entry(
            make_entry(
                "dev",
                "kb",
                path,
                entry_id=eid,
                content_type=ct,
                extraction=ExtractionState(
                    status=status, page_count=n if status == "extracted" else None
                ),
            )
        )
        if status == "extracted":
            for i, body in enumerate(pages_text, start=1):
                await obj.put(keys.derived_text_key("dev", "kb", eid, i), body.encode())

    await doc("guide.md", "G", [P1, P2])  # 2 pages, headings across both
    await doc(
        "report.md",
        "R",
        ["| Region | Sales |\n| --- | --- |\n| EU | 10 |\n| US | 20 |\n\nnotes"],
    )
    await doc("v1.md", "V1", ["line one\nline two\nline three"])
    await doc("v2.md", "V2", ["line one\nline TWO changed\nline three"])
    await doc("scan.pdf", "S", [], status="catalog_only", ct="application/pdf")
    return FsService(cat, obj)


# --- read by section ---


async def test_read_section_spans_to_next_heading() -> None:
    fs = await _seed()
    res = await fs.read_section(_ctx(), "kb", "guide.md", "Setup")
    text = "\n".join(p.text for p in res.pages)
    assert "install steps here" in text
    assert res.range[0] == 1  # "## Setup" is on page 1


async def test_read_section_later_page() -> None:
    fs = await _seed()
    res = await fs.read_section(_ctx(), "kb", "guide.md", "Security")
    assert res.range[0] == 2  # "## Security" is on page 2
    assert "encrypt at rest" in "\n".join(p.text for p in res.pages)


async def test_read_section_not_found() -> None:
    fs = await _seed()
    with pytest.raises(ValidationError, match="section"):
        await fs.read_section(_ctx(), "kb", "guide.md", "Nonexistent")


# --- fs_tables ---


async def test_tables_parsed_from_markdown() -> None:
    fs = await _seed()
    res = await fs.tables(_ctx(), "kb", "report.md")
    assert len(res.tables) == 1
    t = res.tables[0]
    assert t.header == ["Region", "Sales"]
    assert t.rows == [["EU", "10"], ["US", "20"]]
    assert t.page == 1


async def test_tables_none_when_absent() -> None:
    fs = await _seed()
    res = await fs.tables(_ctx(), "kb", "guide.md")
    assert res.tables == []


async def test_tables_catalog_only_raises() -> None:
    fs = await _seed()
    with pytest.raises(CatalogOnlyError):
        await fs.tables(_ctx(), "kb", "scan.pdf")


# --- fs_diff ---


async def test_diff_shows_changes() -> None:
    fs = await _seed()
    res = await fs.diff(_ctx(), "kb", "v1.md", "v2.md")
    assert "-line two" in res.diff
    assert "+line TWO changed" in res.diff
    assert res.truncated is False


async def test_diff_identical_is_empty() -> None:
    fs = await _seed()
    res = await fs.diff(_ctx(), "kb", "v1.md", "v1.md")
    assert res.diff == ""
