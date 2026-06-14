"""The tool contract + shared deps (ADR 0012).

A **Tool** is a unit of MCP capability: a name, the scopes/capabilities it needs,
and a ``register`` that wires its FastMCP function(s). Tools are pluggable like
stores/normalizers — builtins live in ``builtin.py``; third parties ship a
``afs.tools`` entry point. Enforcement, visibility, and audit are applied
uniformly by the middleware (see ``middleware.py``), so a tool never has to
re-implement them.

``register`` receives ``ToolDeps`` — the shared services + a per-call principal
resolver — so tools call the same in-process service layer the REST routes use
(no HTTP self-calls).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from afs_server.auth import TenantContext
    from afs_server.services import FsService, ScratchService
    from afs_server.settings import Settings


@dataclass
class ToolDeps:
    """What a tool needs to do its job: the shared services + the principal."""

    fs: FsService
    scratch: ScratchService
    settings: Settings

    def resolve(self) -> TenantContext:
        """The calling principal (dev now; the OAuth resource server later)."""
        from afs_server.auth import resolve_context

        return resolve_context(self.settings)


@runtime_checkable
class Tool(Protocol):
    """One MCP tool. ``required_scopes``/``required_capabilities`` gate both
    visibility (``tools/list``) and per-call invocation, enforced by the
    middleware — declare them, don't check them yourself."""

    name: str  # flat snake_case
    required_scopes: frozenset[str]
    required_capabilities: frozenset[str]

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        """Wire this tool's FastMCP function(s) onto ``mcp``."""
        ...
