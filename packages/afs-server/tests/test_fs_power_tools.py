"""Tier-1 power tools: fs_tree, fs_find, fs_outline, grep parity (ADR 0012)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from afs_core import keys
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.auth import resolve_dev_context
from afs_server.services import FsService
from afs_server.settings import Settings


def _ctx():
    return resolve_dev_context(Settings())


async def _seed() -> FsService:
    cat, obj = InMemoryCatalogStore(), InMemoryObjectStore()

    async def doc(
        path, entry_id, *, pages=1, ct="text/markdown", size=100, status="extracted", text=""
    ):
        await cat.put_entry(
            make_entry(
                "dev",
                "kb",
                path,
                entry_id=entry_id,
                size=size,
                content_type=ct,
                extraction=ExtractionState(
                    status=status, page_count=pages if status == "extracted" else None
                ),
            )
        )
        if status == "extracted":
            for p in range(1, pages + 1):
                body = text if pages == 1 else f"{text}\n(page {p})"
                await obj.put(keys.derived_text_key("dev", "kb", entry_id, p), body.encode())

    await doc("onboarding/welcome.md", "D1", text="# Welcome\n\nhello\n\n## Setup\ndetails")
    await doc(
        "policies/security.md",
        "D2",
        ct="application/pdf",
        size=5000,
        text="# Security\n\nencrypt everything\n\n## Incidents\nreport fast",
    )
    await doc("policies/leave.pdf", "D3", ct="application/pdf", size=2000, status="catalog_only")
    await doc("eng/arch.md", "D4", text="plain text, no headings here")
    return FsService(cat, obj)


# --- fs_tree ---


async def test_tree_renders_indented_structure() -> None:
    fs = await _seed()
    res = await fs.tree(_ctx(), "kb")
    assert res.files == 4
    assert res.dirs == 3  # onboarding, policies, eng
    assert "policies/" in res.tree
    assert "  security.md" in res.tree  # nested under policies/ at depth 1


async def test_tree_prefix_scopes_subtree() -> None:
    fs = await _seed()
    res = await fs.tree(_ctx(), "kb", prefix="policies/")
    assert res.files == 2
    assert "security.md" in res.tree
    assert "welcome.md" not in res.tree


# --- fs_find ---


async def test_find_by_content_type_prefix() -> None:
    fs = await _seed()
    res = await fs.find(_ctx(), "kb", content_type="application/pdf")
    assert {i.path for i in res.items} == {"policies/security.md", "policies/leave.pdf"}


async def test_find_by_status_and_size() -> None:
    fs = await _seed()
    only_catalog = await fs.find(_ctx(), "kb", status="catalog_only")
    assert [i.path for i in only_catalog.items] == ["policies/leave.pdf"]
    big = await fs.find(_ctx(), "kb", min_size=3000)
    assert [i.path for i in big.items] == ["policies/security.md"]


async def test_find_modified_after() -> None:
    fs = await _seed()
    future = datetime(2099, 1, 1, tzinfo=UTC)
    assert (await fs.find(_ctx(), "kb", modified_after=future)).items == []
    past = datetime(2000, 1, 1, tzinfo=UTC)
    assert len((await fs.find(_ctx(), "kb", modified_after=past)).items) == 4


async def test_find_glob_pattern() -> None:
    fs = await _seed()
    res = await fs.find(_ctx(), "kb", pattern="policies/*")
    assert {i.path for i in res.items} == {"policies/security.md", "policies/leave.pdf"}


# --- fs_outline ---


async def test_outline_extracts_markdown_headings() -> None:
    fs = await _seed()
    res = await fs.outline(_ctx(), "kb", "policies/security.md")
    titles = [(h.level, h.title) for h in res.headings]
    assert (1, "Security") in titles
    assert (2, "Incidents") in titles


async def test_outline_empty_when_no_headings() -> None:
    fs = await _seed()
    res = await fs.outline(_ctx(), "kb", "eng/arch.md")
    assert res.headings == []
    assert res.page_count == 1


async def test_outline_catalog_only_raises() -> None:
    from afs_core.errors import CatalogOnlyError

    fs = await _seed()
    with pytest.raises(CatalogOnlyError):
        await fs.outline(_ctx(), "kb", "policies/leave.pdf")


# --- grep parity ---


async def test_grep_files_with_matches() -> None:
    fs = await _seed()
    res = await fs.grep(_ctx(), "kb", "report", files_with_matches=True)
    assert res.files == ["policies/security.md"]
    assert res.matches == []


async def test_grep_content_type_filter() -> None:
    fs = await _seed()
    # "e" appears in both md and pdf-derived text; restrict to pdf-typed docs
    res = await fs.grep(_ctx(), "kb", "encrypt", content_type="application/pdf")
    assert {m.path for m in res.matches} == {"policies/security.md"}
