"""Builtin tools — the read surface, as registry entries (ADR 0012).

Behaviour is unchanged from the original hand-wired tools; they now declare their
scopes and register through the registry so the middleware enforces + audits them
uniformly, and so third-party tools sit alongside them as equals.

Tools are flat ``snake_case``; the docstring **is** the tool description (it
states the find→read flow and the bounds), per the plan.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError

from afs_core.errors import AfsError

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from fastmcp import FastMCP
    from pydantic import BaseModel

    from afs_server.tools.base import ToolDeps


async def _result(coro: Awaitable[BaseModel]) -> dict[str, Any]:
    """Await a service call; surface expected AfsErrors as MCP ToolErrors."""
    try:
        model = await coro
    except AfsError as err:
        raise ToolError(err.message) from err
    return model.model_dump(mode="json")


class WhoamiTool:
    name = "whoami"
    required_scopes: frozenset[str] = frozenset()
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def whoami() -> dict[str, Any]:
            """Return the calling principal: tenant, scopes, and granted namespaces."""
            ctx = deps.resolve()
            return {
                "tenant_id": ctx.tenant_id,
                "principal_id": ctx.principal_id,
                "scopes": sorted(ctx.scopes),
                "namespaces": sorted(ctx.namespaces) if ctx.namespaces is not None else None,
            }


class FsListTool:
    name = "fs_list"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_list(namespace: str, prefix: str = "", limit: int = 100) -> dict[str, Any]:
            """List catalog entries in a namespace under an optional path prefix.

            Start here to discover documents, then fs_read to fetch their text.
            Returns up to `limit` entries and a `next_cursor` to page further.
            """
            return await _result(
                deps.fs.list_entries(deps.resolve(), namespace, prefix=prefix, limit=limit)
            )


class FsStatTool:
    name = "fs_stat"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_stat(namespace: str, path: str) -> dict[str, Any]:
            """Return one document's catalog record (size, title, extraction status…)."""
            return await _result(deps.fs.stat(deps.resolve(), namespace, path))


class FsReadTool:
    name = "fs_read"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_read(
            namespace: str,
            path: str,
            start_page: int = 1,
            end_page: int | None = None,
            section: str | None = None,
        ) -> dict[str, Any]:
            """Read a bounded page range (<= 20 pages) of a document's extracted text.

            Pass `section` (a heading from fs_outline) to read just that section's
            pages instead of a page range — jump straight to the relevant part. A
            `catalog_only` document exists and is citeable but isn't readable yet —
            you'll get a tool error saying so; you can still reference it by path.
            """
            ctx = deps.resolve()
            if section is not None:
                return await _result(deps.fs.read_section(ctx, namespace, path, section))
            return await _result(
                deps.fs.read(ctx, namespace, path, start_page=start_page, end_page=end_page)
            )


class FsGlobTool:
    name = "fs_glob"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_glob(namespace: str, pattern: str, limit: int = 100) -> dict[str, Any]:
            """Find document paths in a namespace matching a glob (e.g. `**/*.pdf`).

            `*`/`?`/`[seq]` are supported and `*` matches across `/` (recursive).
            Cheaper than fs_grep when you only need paths, not content.
            """
            return await _result(deps.fs.glob(deps.resolve(), namespace, pattern, limit=limit))


class FsGrepTool:
    name = "fs_grep"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_grep(
            namespace: str,
            pattern: str,
            path_glob: str = "*",
            ignore_case: bool = True,
            context_lines: int = 0,
            max_files: int = 200,
            max_matches: int = 100,
            content_type: str | None = None,
            files_with_matches: bool = False,
        ) -> dict[str, Any]:
            """Regex-search documents' extracted text in a namespace (two-stage, bounded).

            `pattern` is a regex; `path_glob` narrows which docs are scanned first, and
            `content_type` filters by MIME (exact or prefix like `application/pdf`).
            Set `files_with_matches: true` for just the matching paths (cheap discovery).
            Results are capped (files / matches / bytes); `truncated: true` means a
            budget was hit — narrow with `path_glob` or a tighter `pattern`. Each hit
            gives `path` + `page` — pass those to fs_read for the full surrounding text.
            """
            return await _result(
                deps.fs.grep(
                    deps.resolve(),
                    namespace,
                    pattern,
                    path_glob=path_glob,
                    ignore_case=ignore_case,
                    context_lines=context_lines,
                    max_files=max_files,
                    max_matches=max_matches,
                    content_type=content_type,
                    files_with_matches=files_with_matches,
                )
            )


class FsTreeTool:
    name = "fs_tree"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_tree(
            namespace: str, prefix: str = "", max_entries: int = 2000
        ) -> dict[str, Any]:
            """Show a namespace as an indented directory tree (like `tree`/`ls -R`).

            The fastest way to grasp a namespace's structure before globbing/reading.
            `prefix` scopes to a subtree; `truncated: true` means the entry cap hit —
            pass a deeper `prefix` to narrow.
            """
            return await _result(
                deps.fs.tree(deps.resolve(), namespace, prefix=prefix, max_entries=max_entries)
            )


class FsFindTool:
    name = "fs_find"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_find(
            namespace: str,
            pattern: str = "*",
            content_type: str | None = None,
            status: str | None = None,
            min_size: int | None = None,
            max_size: int | None = None,
            modified_after: datetime | None = None,
            limit: int = 100,
        ) -> dict[str, Any]:
            """Find documents by path glob + metadata filters (the `find` to fs_grep).

            Filter by `content_type` (exact or prefix), extraction `status`
            (extracted / catalog_only / pending), size bounds, and `modified_after`
            (ISO-8601 date/time, coerced by the schema). Returns each match's path +
            size + type + status + mtime. `truncated: true` means more matched than `limit`.
            """
            return await _result(
                deps.fs.find(
                    deps.resolve(),
                    namespace,
                    pattern=pattern,
                    content_type=content_type,
                    status=status,
                    min_size=min_size,
                    max_size=max_size,
                    modified_after=modified_after,
                    limit=limit,
                )
            )


class FsOutlineTool:
    name = "fs_outline"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_outline(namespace: str, path: str, max_headings: int = 300) -> dict[str, Any]:
            """Return a document's structure: its markdown headings + the page each is on.

            A symbol map for a document — read this first to jump straight to the
            relevant section with fs_read instead of paging through everything. Plain
            documents with no headings return an empty outline.
            """
            return await _result(
                deps.fs.outline(deps.resolve(), namespace, path, max_headings=max_headings)
            )


class FsTablesTool:
    name = "fs_tables"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_tables(namespace: str, path: str) -> dict[str, Any]:
            """Extract the tables in a document as structured rows (header + rows + page).

            Surfaces markdown tables from the extracted text (so it works on whatever
            the extractor produced — best on PDFs/Office via the table-aware rungs).
            Bounded; `truncated: true` means a table/row/page cap was hit.
            """
            return await _result(deps.fs.tables(deps.resolve(), namespace, path))


class FsDiffTool:
    name = "fs_diff"
    required_scopes = frozenset({"fs:read"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def fs_diff(namespace: str, path_a: str, path_b: str) -> dict[str, Any]:
            """Unified diff between two documents' extracted text (compare two files/versions).

            Reads the first pages of each and returns a bounded unified diff (empty
            when identical); `truncated: true` means the line budget was hit.
            """
            return await _result(deps.fs.diff(deps.resolve(), namespace, path_a, path_b))


class ScratchWriteTool:
    name = "scratch_write"
    required_scopes = frozenset({"fs:write:scratch"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def scratch_write(path: str, content: str) -> dict[str, Any]:
            """Write text to your private scratch workspace (overwrites `path`).

            Scratch is your own working area — for notes/intermediate results — not
            the shared corpus, so it never appears in fs_list/fs_grep. Subject to
            your scratch quota; returns your usage after the write.
            """
            return await _result(deps.scratch.write(deps.resolve(), path, content))


class ScratchReadTool:
    name = "scratch_read"
    required_scopes = frozenset({"fs:write:scratch"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def scratch_read(path: str) -> dict[str, Any]:
            """Read back text you wrote to your scratch workspace."""
            return await _result(deps.scratch.read(deps.resolve(), path))


class ScratchListTool:
    name = "scratch_list"
    required_scopes = frozenset({"fs:write:scratch"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def scratch_list(prefix: str = "") -> dict[str, Any]:
            """List paths in your scratch workspace under an optional prefix."""
            return await _result(deps.scratch.list(deps.resolve(), prefix))


class ScratchDeleteTool:
    name = "scratch_delete"
    required_scopes = frozenset({"fs:write:scratch"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def scratch_delete(path: str) -> dict[str, Any]:
            """Delete a scratch object and free its quota."""
            return await _result(deps.scratch.delete(deps.resolve(), path))
