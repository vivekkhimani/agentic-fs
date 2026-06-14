"""Builtin tools — the read surface, as registry entries (ADR 0012).

Behaviour is unchanged from the original hand-wired tools; they now declare their
scopes and register through the registry so the middleware enforces + audits them
uniformly, and so third-party tools sit alongside them as equals.

Tools are flat ``snake_case``; the docstring **is** the tool description (it
states the find→read flow and the bounds), per the plan.
"""

from __future__ import annotations

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
            namespace: str, path: str, start_page: int = 1, end_page: int | None = None
        ) -> dict[str, Any]:
            """Read a bounded page range (<= 20 pages) of a document's extracted text.

            A `catalog_only` document exists and is citeable but isn't readable yet —
            you'll get a tool error saying so; you can still reference it by path.
            """
            return await _result(
                deps.fs.read(
                    deps.resolve(), namespace, path, start_page=start_page, end_page=end_page
                )
            )
