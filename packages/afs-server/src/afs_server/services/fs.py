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
    GlobResponse,
    GrepMatch,
    GrepResponse,
    ReadPage,
    ReadResponse,
)

if TYPE_CHECKING:
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
    ) -> GrepResponse:
        """Two-stage, budgeted regex search over a namespace's derived text.

        Stage 1: the catalog narrows candidates by ``path_glob`` (no full scan).
        Stage 2: scan those docs' derived text, emitting bounded matches. Hitting
        any budget (files/matches/bytes) sets ``truncated`` — narrow the query.
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

        matches: list[GrepMatch] = []
        files_searched = 0
        bytes_scanned = 0
        truncated = False
        for entry in candidates:
            if len(matches) >= max_matches or bytes_scanned >= GREP_BYTE_BUDGET:
                truncated = True
                break
            files_searched += 1
            per_file = 0
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
                if per_file >= max_per_file or len(matches) >= max_matches:
                    break
        return GrepResponse(matches=matches, files_searched=files_searched, truncated=truncated)

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
