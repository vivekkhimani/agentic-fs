"""Tests for the key scheme — the most security-sensitive utility in afs-core."""

from __future__ import annotations

import pytest

from afs_core import keys
from afs_core.errors import InvalidKeyError
from afs_core.keys import Channel


def test_originals_roundtrip() -> None:
    key = keys.originals_key("acme", "handbook", "course-101/intro.pdf")
    assert key == "tenants/acme/handbook/course-101/intro.pdf"
    parsed = keys.parse_key(key)
    assert parsed is not None
    assert parsed.channel is Channel.ORIGINAL
    assert parsed.tenant_id == "acme"
    assert parsed.namespace == "handbook"
    assert parsed.path == "course-101/intro.pdf"


def test_scratch_roundtrip() -> None:
    key = keys.scratch_key("acme", "agent-7", "notes/draft.md")
    assert key == "scratch/acme/agent-7/notes/draft.md"
    parsed = keys.parse_key(key)
    assert parsed is not None
    assert parsed.channel is Channel.SCRATCH
    assert parsed.principal_id == "agent-7"
    assert parsed.path == "notes/draft.md"


def test_derived_text_roundtrip_and_page_padding() -> None:
    key = keys.derived_text_key("acme", "handbook", "01JABCDEF", 7)
    assert key == "derived/text/acme/handbook/01JABCDEF/0007.md"
    parsed = keys.parse_key(key)
    assert parsed is not None
    assert parsed.channel is Channel.DERIVED_TEXT
    assert parsed.doc_id == "01JABCDEF"
    assert parsed.page == 7
    assert parsed.is_metadata is False


def test_derived_text_metadata_sidecar() -> None:
    key = keys.derived_text_metadata_key("acme", "handbook", "01JABCDEF", 7)
    assert key.endswith("0007.md.metadata.json")
    parsed = keys.parse_key(key)
    assert parsed is not None
    assert parsed.is_metadata is True
    assert parsed.page == 7


def test_derived_meta_and_tree() -> None:
    meta = keys.derived_meta_key("acme", "handbook", "01JABCDEF")
    assert meta == "derived/meta/acme/handbook/01JABCDEF/manifest.json"
    assert keys.parse_key(meta).channel is Channel.DERIVED_META  # type: ignore[union-attr]

    tree = keys.tree_key("acme", "handbook")
    assert tree == "derived/tree/acme/handbook.json.zst"
    assert keys.parse_key(tree).channel is Channel.DERIVED_TREE  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "key",
    [
        "tenants/acme/handbook",  # rebuildable from S3: returns None (no relpath)
        "tenants/acme/handbook/../etc/passwd",  # traversal
        "tenants/acme/handbook//evil",  # empty segment
        "tenants/acme/handbook/_private",  # leading-underscore reserved
        "garbage/acme/handbook/x.pdf",  # unknown channel
        "derived/text/acme/handbook/01J/7.md",  # page not zero-padded
        "derived/tree/acme/handbook.json",  # wrong tree suffix
    ],
)
def test_parse_rejects_nonconforming(key: str) -> None:
    assert keys.parse_key(key) is None


@pytest.mark.parametrize("path", ["../escape", "/abs/path", "a/../b", "_hidden/x", "a//b"])
def test_builders_reject_bad_relpath(path: str) -> None:
    with pytest.raises(InvalidKeyError):
        keys.originals_key("acme", "handbook", path)


@pytest.mark.parametrize("bad", ["Acme", "ac me", "-lead", ""])
def test_builders_reject_bad_slug(bad: str) -> None:
    with pytest.raises(InvalidKeyError):
        keys.originals_key(bad, "handbook", "a.pdf")


def test_is_indexable_only_originals() -> None:
    assert keys.is_indexable(keys.originals_key("acme", "ns", "a.pdf")) is True
    assert keys.is_indexable(keys.scratch_key("acme", "p", "a.md")) is False
    assert keys.is_indexable(keys.derived_text_key("acme", "ns", "DOC", 1)) is False
    assert keys.is_indexable(keys.tree_key("acme", "ns")) is False
    assert keys.is_indexable("garbage") is False
