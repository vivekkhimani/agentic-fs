"""The LlamaHub reader → Connector adapter (ADR 0014).

Uses a duck-typed fake reader (no llama-index dependency) — the adapter only needs
``load_data()`` + docs with ``.text``/``.metadata``.
"""

from __future__ import annotations

import pytest

from afs_connector_sdk.connectors.llamahub import LlamaHubConnector
from afs_connector_sdk.registry import build_connector
from afs_core.models import SourceItem
from afs_core.testing.conformance import ConnectorConformance


class FakeDoc:
    def __init__(self, text: str, metadata: dict | None = None) -> None:
        self.text = text
        self.metadata = metadata or {}


class FakeReader:
    """Minimal stand-in for a LlamaHub BaseReader."""

    def __init__(self, docs: list[FakeDoc]) -> None:
        self._docs = docs

    def load_data(self) -> list[FakeDoc]:
        return self._docs


def _connector(*docs: FakeDoc) -> LlamaHubConnector:
    return LlamaHubConnector(reader=FakeReader(list(docs)))


class TestLlamaHubConformance(ConnectorConformance):
    @pytest.fixture
    def connector(self) -> LlamaHubConnector:
        return _connector(
            FakeDoc("hello world", {"file_name": "intro.md"}),
            FakeDoc("second doc", {"file_path": "sub/notes.txt"}),
        )


def test_text_is_ingested_as_markdown() -> None:
    conn = _connector(FakeDoc("the body", {"file_name": "a.md"}))
    item = next(iter(conn.discover()))
    assert item.content_type == "text/markdown"
    assert conn.fetch(item) == b"the body"


def test_path_from_various_metadata_keys() -> None:
    conn = _connector(
        FakeDoc("x", {"file_name": "a.md"}),
        FakeDoc("y", {"file_path": "deep/b.txt"}),
        FakeDoc("z", {"url": "https://site.example/docs/c.html"}),
        FakeDoc("w", {}),  # no metadata → synthesized
    )
    paths = [i.path for i in conn.discover()]
    assert paths == ["a.md", "deep/b.txt", "site.example/docs/c.html", "doc-3.md"]


def test_parent_traversal_is_stripped() -> None:
    conn = _connector(FakeDoc("x", {"file_path": "/../../etc/passwd"}))
    (item,) = list(conn.discover())
    assert item.path == "etc/passwd"
    assert not item.path.startswith("/")
    assert ".." not in item.path.split("/")


def test_duplicate_paths_are_made_unique() -> None:
    conn = _connector(
        FakeDoc("one", {"file_name": "dup.md"}),
        FakeDoc("two", {"file_name": "dup.md"}),
    )
    paths = [i.path for i in conn.discover()]
    assert len(set(paths)) == 2
    assert "dup.md" in paths


def test_version_prefers_metadata_then_hashes() -> None:
    by_meta = next(iter(_connector(FakeDoc("x", {"file_name": "a", "version": "v7"})).discover()))
    by_hash = next(iter(_connector(FakeDoc("x", {"file_name": "a"})).discover()))
    assert by_meta.version == "version:v7"
    assert by_hash.version.startswith("sha256:")


def test_discover_is_repeatable_and_fetch_roundtrips() -> None:
    conn = _connector(
        FakeDoc("alpha", {"file_name": "a.md"}), FakeDoc("beta", {"file_name": "b.md"})
    )
    first = list(conn.discover())
    second = list(conn.discover())
    assert [i.path for i in first] == [i.path for i in second]
    assert conn.fetch(first[1]) == b"beta"


def test_get_content_fallback() -> None:
    class ContentDoc:
        def __init__(self) -> None:
            self.metadata = {"file_name": "c.md"}

        def get_content(self) -> str:
            return "via get_content"

    conn = LlamaHubConnector(reader=FakeReader([ContentDoc()]))  # type: ignore[list-item]
    item = next(iter(conn.discover()))
    assert conn.fetch(item) == b"via get_content"


def test_registry_resolves_llamahub() -> None:
    # Building via the registry needs a reader path; a bogus one fails clearly,
    # proving the name resolves to our adapter (not "unknown connector").
    with pytest.raises((ImportError, AttributeError, ModuleNotFoundError, ValueError)):
        build_connector("llamahub", "nonexistent.module.Reader")


def test_missing_source_and_reader_errors() -> None:
    with pytest.raises(ValueError, match="reader"):
        LlamaHubConnector()


def test_items_are_source_items() -> None:
    item = next(iter(_connector(FakeDoc("x", {"file_name": "a.md"})).discover()))
    assert isinstance(item, SourceItem)
