"""FsService read-path logic, over the in-memory fakes (no infra)."""

from __future__ import annotations

import pytest

from afs_core import keys
from afs_core.errors import (
    CatalogOnlyError,
    DocumentNotFoundError,
    InsufficientScopeError,
    NamespaceNotFoundError,
)
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.auth import TenantContext
from afs_server.services import FsService

_CTX = TenantContext(tenant_id="acme", principal_id="p", scopes=frozenset({"fs:read"}))


@pytest.fixture
def service() -> FsService:
    return FsService(InMemoryCatalogStore(), InMemoryObjectStore())


async def _seed_extracted(svc: FsService, *, text: bytes = b"hello") -> None:
    await svc._catalog.put_entry(
        make_entry(
            "acme",
            "handbook",
            "intro.md",
            entry_id="DOC1",
            extraction=ExtractionState(status="extracted", page_count=1),
        )
    )
    await svc._objects.put(keys.derived_text_key("acme", "handbook", "DOC1", 1), text)


async def test_list_and_stat(service: FsService) -> None:
    await _seed_extracted(service)
    page = await service.list_entries(_CTX, "handbook")
    assert [e.path for e in page.items] == ["intro.md"]
    entry = await service.stat(_CTX, "handbook", "intro.md")
    assert entry.path == "intro.md"


async def test_stat_missing_raises_404(service: FsService) -> None:
    with pytest.raises(DocumentNotFoundError):
        await service.stat(_CTX, "handbook", "nope.md")


async def test_read_returns_pages(service: FsService) -> None:
    await _seed_extracted(service, text=b"hello world")
    resp = await service.read(_CTX, "handbook", "intro.md")
    assert resp.pages[0].text == "hello world"
    assert resp.range == (1, 1)
    assert resp.truncated is False


async def test_read_catalog_only_is_blocked_but_citeable(service: FsService) -> None:
    await service._catalog.put_entry(
        make_entry(
            "acme",
            "handbook",
            "scan.pdf",
            entry_id="DOC2",
            extraction=ExtractionState(status="catalog_only", reason="encrypted_pdf"),
        )
    )
    with pytest.raises(CatalogOnlyError):
        await service.read(_CTX, "handbook", "scan.pdf")


async def test_missing_scope_is_403(service: FsService) -> None:
    ctx = TenantContext(tenant_id="acme", principal_id="p", scopes=frozenset())
    with pytest.raises(InsufficientScopeError):
        await service.list_entries(ctx, "handbook")


async def test_ungranted_namespace_is_404_not_403(service: FsService) -> None:
    ctx = TenantContext(
        tenant_id="acme",
        principal_id="p",
        scopes=frozenset({"fs:read"}),
        namespaces=frozenset({"handbook"}),
    )
    with pytest.raises(NamespaceNotFoundError):
        await service.list_entries(ctx, "secret-ns")
