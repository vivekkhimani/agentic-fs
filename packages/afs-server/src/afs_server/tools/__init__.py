"""Pluggable MCP tools (ADR 0012) — registry + uniform middleware."""

from afs_server.tools.base import Tool, ToolDeps
from afs_server.tools.middleware import ToolMiddleware
from afs_server.tools.registry import build_tools

__all__ = ["Tool", "ToolDeps", "ToolMiddleware", "build_tools"]
