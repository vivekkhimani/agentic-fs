"""MCP tool surface via the FastMCP in-memory client."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from afs_core import keys
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.mcp import build_mcp
from afs_server.services import FsService
from afs_server.settings import Settings


@pytest.fixture
async def client() -> AsyncIterator[Client]:
    catalog, objects = InMemoryCatalogStore(), InMemoryObjectStore()
    await catalog.put_entry(
        make_entry(
            "dev",
            "handbook",
            "intro.md",
            entry_id="DOC1",
            extraction=ExtractionState(status="extracted", page_count=1),
        )
    )
    await objects.put(keys.derived_text_key("dev", "handbook", "DOC1", 1), b"hello world")
    await catalog.put_entry(
        make_entry(
            "dev",
            "handbook",
            "scan.pdf",
            entry_id="DOC2",
            extraction=ExtractionState(status="catalog_only", reason="encrypted"),
        )
    )
    mcp = build_mcp(FsService(catalog, objects), Settings())
    async with Client(mcp) as c:
        yield c


async def test_tools_are_listed(client: Client) -> None:
    names = {t.name for t in await client.list_tools()}
    assert {"whoami", "fs_list", "fs_stat", "fs_read", "fs_glob", "fs_grep"} <= names


async def test_fs_glob(client: Client) -> None:
    res = await client.call_tool("fs_glob", {"namespace": "handbook", "pattern": "*.md"})
    assert res.data["paths"] == ["intro.md"]  # the catalog_only scan.pdf doesn't match


async def test_fs_grep(client: Client) -> None:
    res = await client.call_tool("fs_grep", {"namespace": "handbook", "pattern": "hello"})
    assert res.data["matches"][0]["path"] == "intro.md"
    assert res.data["matches"][0]["text"] == "hello world"
    assert res.data["truncated"] is False


async def test_whoami(client: Client) -> None:
    res = await client.call_tool("whoami", {})
    assert res.data["tenant_id"] == "dev"
    assert "fs:read" in res.data["scopes"]


async def test_fs_list(client: Client) -> None:
    res = await client.call_tool("fs_list", {"namespace": "handbook"})
    assert {e["path"] for e in res.data["items"]} == {"intro.md", "scan.pdf"}


async def test_fs_stat(client: Client) -> None:
    res = await client.call_tool("fs_stat", {"namespace": "handbook", "path": "intro.md"})
    assert res.data["path"] == "intro.md"


async def test_fs_read(client: Client) -> None:
    res = await client.call_tool("fs_read", {"namespace": "handbook", "path": "intro.md"})
    assert res.data["pages"][0]["text"] == "hello world"


async def test_fs_read_catalog_only_is_tool_error(client: Client) -> None:
    with pytest.raises(ToolError):
        await client.call_tool("fs_read", {"namespace": "handbook", "path": "scan.pdf"})
