"""The uniform tool middleware (ADR 0012) — visibility, enforcement, audit.

Applied by the MCP mount to **every** tool (builtin or plugin), so a tool can't
skip it:

- ``on_list_tools`` — claims-filtered visibility: a principal only sees tools
  whose ``required_scopes`` it holds.
- ``on_call_tool`` — per-call enforcement (visibility is UX; this is the gate) +
  a structured audit line.

Capability gating (``required_capabilities``) is declared on tools but enforced
once namespace capabilities are threaded into the principal context; for now only
scopes are gated. Auth is the dev principal today and the OAuth resource server
later — same ``resolve_context`` seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from afs_core.errors import AfsError
from afs_server.auth import resolve_context

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext

    from afs_server.auth import TenantContext
    from afs_server.settings import Settings
    from afs_server.tools.base import Tool

logger = structlog.get_logger("afs_server.tools")


class ToolMiddleware(Middleware):
    def __init__(self, tools_by_name: dict[str, Tool], settings: Settings) -> None:
        self._tools = tools_by_name
        self._settings = settings

    def _allowed(self, tool: Tool, ctx: TenantContext) -> bool:
        return tool.required_scopes <= ctx.scopes

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        tools = await call_next(context)
        try:
            ctx = resolve_context(self._settings)
        except AfsError:
            return []  # unauthenticated → nothing is visible
        return [
            t for t in tools if t.name not in self._tools or self._allowed(self._tools[t.name], ctx)
        ]

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        name = context.message.name
        tool = self._tools.get(name)
        try:
            ctx = resolve_context(self._settings)
        except AfsError as err:
            raise ToolError(str(err)) from err

        if tool is not None and not self._allowed(tool, ctx):
            missing = sorted(tool.required_scopes - ctx.scopes)
            logger.warning("tool denied", tool=name, principal=ctx.principal_id, missing=missing)
            raise ToolError(f"missing required scope(s): {', '.join(missing)}")

        logger.info("tool call", tool=name, tenant=ctx.tenant_id, principal=ctx.principal_id)
        return await call_next(context)
