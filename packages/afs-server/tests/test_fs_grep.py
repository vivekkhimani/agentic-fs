"""fs_grep + fs_glob (two-stage, budgeted) on the read-path service."""

from __future__ import annotations

import pytest

from afs_core import keys
from afs_core.errors import ValidationError
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.auth import TenantContext
from afs_server.services import FsService

CTX = TenantContext(
    tenant_id="dev", principal_id="p", scopes=frozenset({"fs:read"}), namespaces=None
)


async def _seed() -> FsService:
    cat, obj = InMemoryCatalogStore(), InMemoryObjectStore()

    async def doc(path: str, entry_id: str, pages: list[str]) -> None:
        await cat.put_entry(
            make_entry(
                "dev",
                "ns",
                path,
                entry_id=entry_id,
                extraction=ExtractionState(status="extracted", page_count=len(pages)),
            )
        )
        for i, text in enumerate(pages, 1):
            await obj.put(keys.derived_text_key("dev", "ns", entry_id, i), text.encode())

    await doc("a.md", "A", ["alpha beta\ngamma", "delta beta"])
    await doc("b.md", "B", ["zeta\nbeta only here"])
    await doc("notes/c.md", "C", ["nothing here"])
    # a catalog_only doc has no derived text — grep must skip it
    await cat.put_entry(
        make_entry(
            "dev",
            "ns",
            "scan.pdf",
            entry_id="D",
            extraction=ExtractionState(status="catalog_only", reason="x"),
        )
    )
    return FsService(cat, obj)


async def test_grep_across_docs_and_pages() -> None:
    fs = await _seed()
    res = await fs.grep(CTX, "ns", r"beta")
    hits = {(m.path, m.page, m.line) for m in res.matches}
    assert ("a.md", 1, 1) in hits  # "alpha beta"
    assert ("a.md", 2, 1) in hits  # "delta beta"
    assert ("b.md", 1, 2) in hits  # "beta only here"
    assert res.truncated is False
    assert all(m.path != "scan.pdf" for m in res.matches)  # catalog_only never scanned


async def test_grep_path_glob_narrows_candidates() -> None:
    fs = await _seed()
    res = await fs.grep(CTX, "ns", r"beta", path_glob="a.*")
    assert {m.path for m in res.matches} == {"a.md"}


async def test_grep_truncates_on_budget() -> None:
    fs = await _seed()
    res = await fs.grep(CTX, "ns", r"beta", max_matches=1)
    assert len(res.matches) == 1 and res.truncated is True


async def test_grep_context_lines() -> None:
    fs = await _seed()
    res = await fs.grep(CTX, "ns", r"gamma", context_lines=1)
    match = next(m for m in res.matches if m.path == "a.md")
    assert match.before == ["alpha beta"] and match.after == []  # gamma is last line


async def test_grep_invalid_regex_is_validation_error() -> None:
    fs = await _seed()
    with pytest.raises(ValidationError):
        await fs.grep(CTX, "ns", r"(unclosed")


async def test_grep_signals_truncation_when_candidate_cap_hit() -> None:
    # max_files caps stage-1 candidates; grep must report truncated rather than
    # silently scanning only the first N docs (ADR 0015). "beta" is in a.md + b.md.
    fs = await _seed()
    res = await fs.grep(CTX, "ns", r"beta", max_files=1)
    assert res.files_searched == 1
    assert res.truncated is True


async def test_grep_literal_fast_path_matches_regex_engine() -> None:
    # A literal pattern takes the page-prefilter path; results must be identical
    # to a non-literal regex that matches the same text.
    fs = await _seed()
    literal = await fs.grep(CTX, "ns", r"beta")
    regexp = await fs.grep(CTX, "ns", r"b[e]ta")  # same matches, but not literal
    assert {(m.path, m.page, m.line) for m in literal.matches} == {
        (m.path, m.page, m.line) for m in regexp.matches
    }


async def test_grep_literal_case_insensitive_prefilter() -> None:
    # The literal prefilter is case-folded under ignore_case — an upper-case query
    # still finds lower-case text (and vice versa).
    fs = await _seed()
    res = await fs.grep(CTX, "ns", r"BETA", ignore_case=True)
    assert {m.path for m in res.matches} == {"a.md", "b.md"}
    none = await fs.grep(CTX, "ns", r"BETA", ignore_case=False)
    assert none.matches == []


async def test_glob_matches_across_separators() -> None:
    fs = await _seed()
    res = await fs.glob(CTX, "ns", "*.md")
    assert {"a.md", "b.md", "notes/c.md"} <= set(res.paths)  # * spans '/'
    scoped = await fs.glob(CTX, "ns", "notes/*")
    assert scoped.paths == ["notes/c.md"]
