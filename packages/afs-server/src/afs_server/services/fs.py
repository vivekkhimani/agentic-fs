"""The read-path service: list / stat / read over the catalog + object stores.

Authority is enforced here (scope + namespace), every read is bounded, and misses
return 404 (no enumeration) — the load-bearing rules from the plan (§2.1, §6).
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING

from afs_core import keys
from afs_core.errors import (
    CatalogOnlyError,
    DocumentNotFoundError,
    NamespaceNotFoundError,
    ValidationError,
)
from afs_server.schemas import (
    EntryPage,
    FindItem,
    FindResponse,
    GlobResponse,
    GrepMatch,
    GrepResponse,
    OutlineHeading,
    OutlineResponse,
    ReadPage,
    ReadResponse,
    TreeResponse,
)

if TYPE_CHECKING:
    from datetime import datetime

    from afs_core.contracts import CatalogStore, ObjectStore
    from afs_core.models import CatalogEntry
    from afs_server.auth import TenantContext

MAX_READ_PAGES = 20

# grep/glob budgets — hard ceilings so a tool call can't run unboundedly or blow
# the agent's context window. Tool params may request less, never more.
MAX_GLOB_RESULTS = 500
MAX_GREP_FILES = 200  # candidate docs scanned (stage 1)
MAX_GREP_MATCHES = 100  # total matches returned
MAX_GREP_MATCHES_PER_FILE = 10
MAX_GREP_CONTEXT_LINES = 5
GREP_BYTE_BUDGET = 5_000_000  # stop scanning derived text past this
GREP_LINE_CAP = 300  # truncate each emitted line

MAX_TREE_ENTRIES = 2000  # paths walked into the tree before truncating
MAX_FIND_RESULTS = 500
MAX_OUTLINE_PAGES = 50  # pages scanned for headings
MAX_OUTLINE_HEADINGS = 300
OUTLINE_TITLE_CAP = 200

# Markdown ATX headings (`#`..`######`) — extraction (esp. docling) emits markdown,
# so this is a precise structure signal; plain-text docs simply yield no headings.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")


def _glob_prefix(pattern: str) -> str:
    """The literal path prefix before the first wildcard — narrows the catalog
    query so glob/grep don't scan the whole namespace."""
    literal: list[str] = []
    for ch in pattern:
        if ch in "*?[":
            break
        literal.append(ch)
    joined = "".join(literal)
    return joined[: joined.rfind("/") + 1] if "/" in joined else ""


def _matches_type(actual: str, wanted: str) -> bool:
    """Content-type filter: exact, or a prefix like ``image/`` / ``application``."""
    return actual == wanted or actual.startswith(wanted)


def _render_tree(paths: list[str], prefix: str) -> tuple[str, int, int]:
    """Render sorted paths as an indented tree (2 spaces/level, dirs end with ``/``).
    Returns ``(text, dir_count, file_count)``. Paths are shown relative to ``prefix``."""
    plen = len(prefix)
    tree: dict = {}
    files = 0
    for path in sorted(paths):
        rel = path[plen:] if prefix and path.startswith(prefix) else path
        parts = [p for p in rel.split("/") if p]
        if not parts:
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("__files__", []).append(parts[-1])
        files += 1

    lines: list[str] = []
    dirs = 0

    def walk(node: dict, depth: int) -> None:
        nonlocal dirs
        for name in sorted(k for k in node if k != "__files__"):
            lines.append(f"{'  ' * depth}{name}/")
            dirs += 1
            walk(node[name], depth + 1)
        for fname in sorted(node.get("__files__", [])):
            lines.append(f"{'  ' * depth}{fname}")

    walk(tree, 0)
    return "\n".join(lines), dirs, files


class FsService:
    def __init__(self, catalog: CatalogStore, objects: ObjectStore) -> None:
        self._catalog = catalog
        self._objects = objects

    def _authorize(self, ctx: TenantContext, namespace: str) -> None:
        ctx.require_scope("fs:read")
        if not ctx.allows_namespace(namespace):
            # 404, not 403 — a caller cannot tell "not granted" from "does not exist".
            raise NamespaceNotFoundError("namespace not found", detail={"namespace": namespace})

    async def list_entries(
        self,
        ctx: TenantContext,
        namespace: str,
        *,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 100,
    ) -> EntryPage:
        self._authorize(ctx, namespace)
        return await self._catalog.list_entries(
            ctx.tenant_id, namespace, prefix=prefix, cursor=cursor, limit=limit
        )

    async def stat(self, ctx: TenantContext, namespace: str, path: str):
        self._authorize(ctx, namespace)
        keys.validate_relpath(path)
        entry = await self._catalog.get_entry(ctx.tenant_id, namespace, path)
        if entry is None:
            raise DocumentNotFoundError("document not found", detail={"path": path})
        return entry

    async def read(
        self,
        ctx: TenantContext,
        namespace: str,
        path: str,
        *,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> ReadResponse:
        entry = await self.stat(ctx, namespace, path)

        if entry.extraction.status != "extracted":
            raise CatalogOnlyError(
                "this document exists but isn't readable yet — you can still cite it",
                detail={"path": path, "status": entry.extraction.status},
            )

        page_count = entry.extraction.page_count or 0
        start = max(1, start_page)
        end = page_count if end_page is None else min(end_page, page_count)
        if end - start + 1 > MAX_READ_PAGES:
            end = start + MAX_READ_PAGES - 1
        truncated = end < page_count or (end_page is not None and end_page > page_count)

        pages: list[ReadPage] = []
        for page in range(start, end + 1):
            key = keys.derived_text_key(ctx.tenant_id, namespace, entry.entry_id, page)
            raw = await self._objects.get(key)
            pages.append(ReadPage(page=page, text=raw.decode("utf-8")))

        return ReadResponse(
            path=path,
            pages=pages,
            page_count=page_count,
            range=(start, end if end >= start else start),
            truncated=truncated,
        )

    async def glob(
        self, ctx: TenantContext, namespace: str, pattern: str, *, limit: int = 100
    ) -> GlobResponse:
        """Catalog paths matching a glob (``*`` matches across ``/`` — recursive)."""
        self._authorize(ctx, namespace)
        limit = min(max(1, limit), MAX_GLOB_RESULTS)
        entries = await self._match_entries(ctx, namespace, pattern, limit)
        return GlobResponse(paths=[e.path for e in entries])

    async def grep(
        self,
        ctx: TenantContext,
        namespace: str,
        pattern: str,
        *,
        path_glob: str = "*",
        ignore_case: bool = True,
        context_lines: int = 0,
        max_files: int = MAX_GREP_FILES,
        max_matches: int = MAX_GREP_MATCHES,
        max_matches_per_file: int = MAX_GREP_MATCHES_PER_FILE,
        content_type: str | None = None,
        files_with_matches: bool = False,
    ) -> GrepResponse:
        """Two-stage, budgeted regex search over a namespace's derived text.

        Stage 1: the catalog narrows candidates by ``path_glob`` (and optionally
        ``content_type``; no full scan). Stage 2: scan those docs' derived text,
        emitting bounded matches. ``files_with_matches`` returns just the matching
        paths (and stops at each doc's first hit — cheap discovery). Hitting any
        budget (files/matches/bytes) sets ``truncated`` — narrow the query.
        """
        self._authorize(ctx, namespace)
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as err:
            raise ValidationError(f"invalid regex: {err}", detail={"pattern": pattern}) from err

        max_files = min(max(1, max_files), MAX_GREP_FILES)
        max_matches = min(max(1, max_matches), MAX_GREP_MATCHES)
        max_per_file = min(max(1, max_matches_per_file), MAX_GREP_MATCHES_PER_FILE)
        context_lines = min(max(0, context_lines), MAX_GREP_CONTEXT_LINES)

        candidates = await self._match_entries(
            ctx, namespace, path_glob, max_files, extracted_only=True
        )
        if content_type:
            candidates = [e for e in candidates if _matches_type(e.content_type, content_type)]

        matches: list[GrepMatch] = []
        files: list[str] = []
        files_searched = 0
        bytes_scanned = 0
        truncated = False
        for entry in candidates:
            if len(matches) >= max_matches or bytes_scanned >= GREP_BYTE_BUDGET:
                truncated = True
                break
            files_searched += 1
            per_file = 0
            hit_in_file = False
            for page_no in range(1, (entry.extraction.page_count or 0) + 1):
                if bytes_scanned >= GREP_BYTE_BUDGET:
                    truncated = True
                    break
                key = keys.derived_text_key(ctx.tenant_id, namespace, entry.entry_id, page_no)
                raw = await self._objects.get(key)
                bytes_scanned += len(raw)
                lines = raw.decode("utf-8", "replace").splitlines()
                for i, line in enumerate(lines):
                    if not regex.search(line):
                        continue
                    if files_with_matches:
                        files.append(entry.path)
                        hit_in_file = True
                        break
                    matches.append(
                        GrepMatch(
                            path=entry.path,
                            page=page_no,
                            line=i + 1,
                            text=line[:GREP_LINE_CAP],
                            before=[
                                s[:GREP_LINE_CAP] for s in lines[max(0, i - context_lines) : i]
                            ],
                            after=[s[:GREP_LINE_CAP] for s in lines[i + 1 : i + 1 + context_lines]],
                        )
                    )
                    per_file += 1
                    if per_file >= max_per_file or len(matches) >= max_matches:
                        break
                if hit_in_file or per_file >= max_per_file or len(matches) >= max_matches:
                    break
        return GrepResponse(
            matches=matches, files=files, files_searched=files_searched, truncated=truncated
        )

    async def tree(
        self,
        ctx: TenantContext,
        namespace: str,
        *,
        prefix: str = "",
        max_entries: int = MAX_TREE_ENTRIES,
    ) -> TreeResponse:
        """An indented tree of a namespace (optionally under ``prefix``)."""
        self._authorize(ctx, namespace)
        max_entries = min(max(1, max_entries), MAX_TREE_ENTRIES)
        paths: list[str] = []
        cursor: str | None = None
        truncated = False
        while True:
            page = await self._catalog.list_entries(
                ctx.tenant_id, namespace, prefix=prefix, cursor=cursor, limit=200
            )
            for entry in page.items:
                paths.append(entry.path)
                if len(paths) >= max_entries:
                    truncated = bool(page.next_cursor) or False
                    break
            cursor = page.next_cursor
            if not cursor or len(paths) >= max_entries:
                break
        rendered, dirs, files = _render_tree(paths, prefix)
        return TreeResponse(tree=rendered, dirs=dirs, files=files, truncated=truncated)

    async def find(
        self,
        ctx: TenantContext,
        namespace: str,
        *,
        pattern: str = "*",
        content_type: str | None = None,
        status: str | None = None,
        min_size: int | None = None,
        max_size: int | None = None,
        modified_after: datetime | None = None,
        limit: int = 100,
    ) -> FindResponse:
        """Glob + metadata filters over the catalog (size / type / status / mtime)."""
        self._authorize(ctx, namespace)
        limit = min(max(1, limit), MAX_FIND_RESULTS)
        prefix = _glob_prefix(pattern)
        items: list[FindItem] = []
        cursor: str | None = None
        truncated = False
        while len(items) < limit:
            page = await self._catalog.list_entries(
                ctx.tenant_id, namespace, prefix=prefix, cursor=cursor, limit=100
            )
            for e in page.items:
                if not fnmatchcase(e.path, pattern):
                    continue
                if content_type and not _matches_type(e.content_type, content_type):
                    continue
                if status and e.extraction.status != status:
                    continue
                if min_size is not None and e.size < min_size:
                    continue
                if max_size is not None and e.size > max_size:
                    continue
                if modified_after is not None and e.updated_at < modified_after:
                    continue
                items.append(
                    FindItem(
                        path=e.path,
                        size=e.size,
                        content_type=e.content_type,
                        status=e.extraction.status,
                        updated_at=e.updated_at.isoformat(),
                    )
                )
                if len(items) >= limit:
                    truncated = bool(page.next_cursor)
                    break
            cursor = page.next_cursor
            if not cursor:
                break
        return FindResponse(items=items, truncated=truncated)

    async def outline(
        self,
        ctx: TenantContext,
        namespace: str,
        path: str,
        *,
        max_headings: int = MAX_OUTLINE_HEADINGS,
    ) -> OutlineResponse:
        """A document's markdown-heading structure + page map (a symbol map)."""
        entry = await self.stat(ctx, namespace, path)
        if entry.extraction.status != "extracted":
            raise CatalogOnlyError(
                "this document exists but isn't readable yet — you can still cite it",
                detail={"path": path, "status": entry.extraction.status},
            )
        max_headings = min(max(1, max_headings), MAX_OUTLINE_HEADINGS)
        page_count = entry.extraction.page_count or 0
        scan_pages = min(page_count, MAX_OUTLINE_PAGES)
        headings: list[OutlineHeading] = []
        truncated = page_count > scan_pages
        for page_no in range(1, scan_pages + 1):
            if len(headings) >= max_headings:
                truncated = True
                break
            key = keys.derived_text_key(ctx.tenant_id, namespace, entry.entry_id, page_no)
            raw = await self._objects.get(key)
            for line in raw.decode("utf-8", "replace").splitlines():
                m = _HEADING_RE.match(line)
                if not m:
                    continue
                headings.append(
                    OutlineHeading(
                        level=len(m.group(1)),
                        title=m.group(2)[:OUTLINE_TITLE_CAP],
                        page=page_no,
                    )
                )
                if len(headings) >= max_headings:
                    truncated = True
                    break
        return OutlineResponse(
            path=path, page_count=page_count, headings=headings, truncated=truncated
        )

    async def _match_entries(
        self,
        ctx: TenantContext,
        namespace: str,
        pattern: str,
        limit: int,
        *,
        extracted_only: bool = False,
    ) -> list[CatalogEntry]:
        """The coarse filter: catalog entries whose path matches ``pattern``. Narrows
        the catalog query to the glob's literal prefix, then fnmatches the full path."""
        prefix = _glob_prefix(pattern)
        out: list[CatalogEntry] = []
        cursor: str | None = None
        while len(out) < limit:
            page = await self._catalog.list_entries(
                ctx.tenant_id, namespace, prefix=prefix, cursor=cursor, limit=100
            )
            for entry in page.items:
                if extracted_only and entry.extraction.status != "extracted":
                    continue
                if fnmatchcase(entry.path, pattern):
                    out.append(entry)
                    if len(out) >= limit:
                        break
            cursor = page.next_cursor
            if not cursor:
                break
        return out
