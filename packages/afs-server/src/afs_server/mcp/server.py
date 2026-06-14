"""The MCP mount — registry-driven tools + uniform middleware (ADR 0012).

Tools come from the pluggable registry (builtins + ``afs.tools`` plugins), share
the same in-process services the REST routes use (no HTTP self-calls, plan §7),
and are all wrapped by ``ToolMiddleware`` for visibility, scope enforcement, and
audit. Adding a tool is a registry entry, not an edit here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import FastMCP

from afs_server.auth import build_resource_auth, build_token_verifier
from afs_server.tools import ToolDeps, ToolMiddleware, build_tools

if TYPE_CHECKING:
    from fastmcp.server.auth import TokenVerifier

    from afs_server.services import FsService, ScratchService
    from afs_server.settings import Settings


def build_mcp(
    fs: FsService,
    settings: Settings,
    scratch: ScratchService,
    *,
    token_verifier: TokenVerifier | None = None,
) -> FastMCP:
    # Under oidc, wrap the mount in a RemoteAuthProvider: the transport verifies
    # bearer tokens and serves Protected Resource Metadata (RFC 9728); the
    # middleware then maps the verified token to a principal. Dev → no auth
    # provider, static dev principal. Reuse a shared verifier when given (one
    # JWKS cache across REST + MCP), else build from settings.
    verifier = token_verifier or build_token_verifier(settings)
    mcp: FastMCP = FastMCP("agentic-fs", auth=build_resource_auth(settings, verifier))
    deps = ToolDeps(fs=fs, scratch=scratch, settings=settings)
    tools = build_tools()
    for tool in tools:
        tool.register(mcp, deps)
    mcp.add_middleware(ToolMiddleware({t.name: t for t in tools}, settings))
    return mcp
