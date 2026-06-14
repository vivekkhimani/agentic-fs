"""Local filesystem connector — crawl a directory tree.

Zero dependencies; the reference connector and the easiest way to dogfood the
whole ingest path (point it at a folder of docs and read them back over MCP).
"""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator
from pathlib import Path

from afs_core.models import SourceItem


class LocalConnector:
    name = "local"

    def __init__(self, source: str, *, follow_symlinks: str = "false") -> None:
        self._root = Path(source).expanduser().resolve()
        if not self._root.is_dir():
            raise ValueError(f"source is not a directory: {self._root}")
        # Options arrive as strings from the CLI (`--opt follow_symlinks=true`).
        self._follow = str(follow_symlinks).lower() in {"1", "true", "yes"}

    def discover(self) -> Iterator[SourceItem]:
        for path in sorted(self._root.rglob("*")):
            rel = path.relative_to(self._root)
            # Skip hidden files and dot-directories (.git, .DS_Store, …).
            if any(part.startswith(".") for part in rel.parts):
                continue
            if path.is_symlink() and not self._follow:
                continue
            if not path.is_file():
                continue
            stat = path.stat()
            yield SourceItem(
                path=rel.as_posix(),
                locator=str(path),
                size=stat.st_size,
                content_type=mimetypes.guess_type(path.name)[0],
                version=f"mtime:{int(stat.st_mtime)}:{stat.st_size}",
            )

    def fetch(self, item: SourceItem) -> bytes:
        return Path(item.locator).read_bytes()
