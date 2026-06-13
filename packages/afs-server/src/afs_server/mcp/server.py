"""The MCP tool surface (FastMCP), backed by the same ``FsService`` the REST
routes use — shared in-process, no HTTP self-calls (plan §7).

This slice exposes the read-path tools (`whoami`, `fs_list`, `fs_stat`,
`fs_read`) under the dev principal. The full middleware chain (per-connection
JWKS auth, claims-filtered `tools/list`, budgets, audit) and the remaining tools
(`fs_glob`/`fs_grep`/`fs_search`/`scratch_*`) land with their services.

Tools are flat `snake_case`; the docstring **is** the tool description (it states
the find→read flow and the bounds), per the plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from afs_core.errors import AfsError
from afs_server.auth import resolve_context

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from pydantic import BaseModel

    from afs_server.services import FsService
    from afs_server.settings import Settings


async def _result(coro: Awaitable[BaseModel]) -> dict[str, Any]:
    """Await a service call; surface expected AfsErrors as MCP ToolErrors."""
    try:
        model = await coro
    except AfsError as err:
        raise ToolError(err.message) from err
    return model.model_dump(mode="json")


def build_mcp(fs: FsService, settings: Settings) -> FastMCP:
    mcp: FastMCP = FastMCP("agentic-fs")

    @mcp.tool
    async def whoami() -> dict[str, Any]:
        """Return the calling principal: tenant, scopes, and granted namespaces."""
        ctx = resolve_context(settings)
        return {
            "tenant_id": ctx.tenant_id,
            "principal_id": ctx.principal_id,
            "scopes": sorted(ctx.scopes),
            "namespaces": sorted(ctx.namespaces) if ctx.namespaces is not None else None,
        }

    @mcp.tool
    async def fs_list(namespace: str, prefix: str = "", limit: int = 100) -> dict[str, Any]:
        """List catalog entries in a namespace under an optional path prefix.

        Start here to discover documents, then fs_read to fetch their text.
        Returns up to `limit` entries and a `next_cursor` to page further.
        """
        return await _result(
            fs.list_entries(resolve_context(settings), namespace, prefix=prefix, limit=limit)
        )

    @mcp.tool
    async def fs_stat(namespace: str, path: str) -> dict[str, Any]:
        """Return one document's catalog record (size, title, extraction status…)."""
        return await _result(fs.stat(resolve_context(settings), namespace, path))

    @mcp.tool
    async def fs_read(
        namespace: str, path: str, start_page: int = 1, end_page: int | None = None
    ) -> dict[str, Any]:
        """Read a bounded page range (<= 20 pages) of a document's extracted text.

        A `catalog_only` document exists and is citeable but isn't readable yet —
        you'll get a tool error saying so; you can still reference it by path.
        """
        return await _result(
            fs.read(
                resolve_context(settings), namespace, path, start_page=start_page, end_page=end_page
            )
        )

    return mcp
