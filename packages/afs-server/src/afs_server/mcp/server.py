"""The MCP mount — registry-driven tools + uniform middleware (ADR 0012).

Tools come from the pluggable registry (builtins + ``afs.tools`` plugins), share
the same in-process services the REST routes use (no HTTP self-calls, plan §7),
and are all wrapped by ``ToolMiddleware`` for visibility, scope enforcement, and
audit. Adding a tool is a registry entry, not an edit here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import FastMCP

from afs_server.tools import ToolDeps, ToolMiddleware, build_tools

if TYPE_CHECKING:
    from afs_server.services import FsService, ScratchService
    from afs_server.settings import Settings


def build_mcp(fs: FsService, settings: Settings, scratch: ScratchService) -> FastMCP:
    mcp: FastMCP = FastMCP("agentic-fs")
    deps = ToolDeps(fs=fs, scratch=scratch, settings=settings)
    tools = build_tools()
    for tool in tools:
        tool.register(mcp, deps)
    mcp.add_middleware(ToolMiddleware({t.name: t for t in tools}, settings))
    return mcp
