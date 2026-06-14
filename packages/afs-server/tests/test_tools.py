"""The pluggable tool registry + uniform middleware (ADR 0012)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore
from afs_server.services import FsService, ScratchService
from afs_server.settings import Settings
from afs_server.tools import ToolDeps, ToolMiddleware, build_tools


def test_build_tools_includes_builtins_with_scopes() -> None:
    tools = {t.name: t for t in build_tools()}
    assert {"whoami", "fs_list", "fs_stat", "fs_read"} <= set(tools)
    assert tools["fs_read"].required_scopes == frozenset({"fs:read"})
    assert tools["whoami"].required_scopes == frozenset()  # everyone can call whoami


class _NeedsBogusScope:
    """A tool the dev principal can't use (dev lacks 'bogus:scope')."""

    name = "needs_bogus"
    required_scopes = frozenset({"bogus:scope"})
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def needs_bogus() -> dict:
            """should never be reachable by the dev principal"""
            return {"ok": True}


class _Firehose:
    """A tool with no caps of its own — the per-call budget is its only guard."""

    name = "firehose"
    required_scopes: frozenset[str] = frozenset()
    required_capabilities: frozenset[str] = frozenset()

    def register(self, mcp: FastMCP, deps: ToolDeps) -> None:
        @mcp.tool
        async def firehose(size: int) -> dict:
            """returns `size` bytes of payload, unbounded"""
            return {"blob": "x" * size}


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    cat, obj = InMemoryCatalogStore(), InMemoryObjectStore()
    deps = ToolDeps(fs=FsService(cat, obj), scratch=ScratchService(cat, obj), settings=Settings())
    mcp: FastMCP = FastMCP("t")
    tools = [*build_tools(), _NeedsBogusScope(), _Firehose()]
    for tool in tools:
        tool.register(mcp, deps)
    # A small budget so the test needn't materialize the 256 KiB default.
    settings = Settings(tool_max_result_bytes=1024)
    mcp.add_middleware(ToolMiddleware({t.name: t for t in tools}, settings))
    async with Client(mcp) as c:
        yield c


async def test_list_is_visibility_filtered(client: Client) -> None:
    names = {t.name for t in await client.list_tools()}
    assert {"whoami", "fs_list"} <= names  # dev has fs:read
    assert "needs_bogus" not in names  # hidden — dev lacks the scope


async def test_call_is_scope_enforced(client: Client) -> None:
    with pytest.raises(ToolError, match="scope"):
        await client.call_tool("needs_bogus", {})


async def test_allowed_tool_still_runs(client: Client) -> None:
    res = await client.call_tool("whoami", {})
    assert res.data["tenant_id"] == "dev"


async def test_under_budget_result_passes(client: Client) -> None:
    res = await client.call_tool("firehose", {"size": 100})
    assert len(res.data["blob"]) == 100


async def test_over_budget_result_is_rejected(client: Client) -> None:
    with pytest.raises(ToolError, match="per-call budget"):
        await client.call_tool("firehose", {"size": 4096})
