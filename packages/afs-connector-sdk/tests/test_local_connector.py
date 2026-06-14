"""Local FS connector — certified against the afs-core kit, plus its specifics."""

from __future__ import annotations

from pathlib import Path

import pytest

from afs_connector_sdk.connectors.local import LocalConnector
from afs_core.testing import ConnectorConformance


def _populate(root: Path) -> None:
    (root / "a.md").write_text("alpha")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("beta beta")


class TestLocalConnector(ConnectorConformance):
    @pytest.fixture
    def connector(self, tmp_path: Path) -> LocalConnector:
        _populate(tmp_path)
        return LocalConnector(str(tmp_path))


def test_discovers_nested_relative_paths(tmp_path: Path) -> None:
    _populate(tmp_path)
    paths = {item.path for item in LocalConnector(str(tmp_path)).discover()}
    assert paths == {"a.md", "sub/b.txt"}


def test_skips_hidden_files_and_dot_dirs(tmp_path: Path) -> None:
    _populate(tmp_path)
    (tmp_path / ".secret").write_text("nope")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("nope")
    paths = {item.path for item in LocalConnector(str(tmp_path)).discover()}
    assert paths == {"a.md", "sub/b.txt"}


def test_fetch_roundtrips_bytes(tmp_path: Path) -> None:
    _populate(tmp_path)
    connector = LocalConnector(str(tmp_path))
    item = next(i for i in connector.discover() if i.path == "a.md")
    assert connector.fetch(item) == b"alpha"
    assert item.content_type == "text/markdown"


def test_rejects_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(ValueError, match="not a directory"):
        LocalConnector(str(f))
