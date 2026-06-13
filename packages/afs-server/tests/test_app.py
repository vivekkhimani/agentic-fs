"""REST surface via TestClient, with the in-memory fakes injected."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from afs_core import keys
from afs_core.models import ExtractionState
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore, make_entry
from afs_server.app import create_app
from afs_server.dependencies import get_catalog, get_fs_service, get_ingest_service
from afs_server.extraction import build_pipeline
from afs_server.services import FsService, IngestService


def _seed(catalog: InMemoryCatalogStore, objects: InMemoryObjectStore) -> None:
    async def go() -> None:
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

    asyncio.run(go())


@pytest.fixture
def client() -> Iterator[TestClient]:
    catalog, objects = InMemoryCatalogStore(), InMemoryObjectStore()
    _seed(catalog, objects)
    app = create_app()
    app.dependency_overrides[get_fs_service] = lambda: FsService(catalog, objects)
    app.dependency_overrides[get_ingest_service] = lambda: IngestService(
        catalog, objects, build_pipeline()
    )
    app.dependency_overrides[get_catalog] = lambda: catalog
    with TestClient(app) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    r = client.get("/v1/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz_ok(client: TestClient) -> None:
    r = client.get("/v1/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_me_dev_principal(client: TestClient) -> None:
    r = client.get("/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "dev"
    assert "fs:read" in body["scopes"]


def test_list_entries(client: TestClient) -> None:
    r = client.get("/v1/fs/handbook/entries")
    assert r.status_code == 200
    paths = {e["path"] for e in r.json()["items"]}
    assert paths == {"intro.md", "scan.pdf"}


def test_stat_found_and_missing(client: TestClient) -> None:
    assert client.get("/v1/fs/handbook/stat", params={"path": "intro.md"}).status_code == 200
    miss = client.get("/v1/fs/handbook/stat", params={"path": "nope.md"})
    assert miss.status_code == 404
    assert miss.headers["content-type"].startswith("application/problem+json")
    assert miss.json()["code"] == "document_not_found"


def test_read_doc(client: TestClient) -> None:
    r = client.get("/v1/fs/handbook/doc", params={"path": "intro.md"})
    assert r.status_code == 200
    assert r.json()["pages"][0]["text"] == "hello world"


def test_read_catalog_only_returns_422(client: TestClient) -> None:
    r = client.get("/v1/fs/handbook/doc", params={"path": "scan.pdf"})
    assert r.status_code == 422
    assert r.json()["code"] == "catalog_only"


def test_ingest_then_read_round_trip(client: TestClient) -> None:
    put = client.put(
        "/v1/ingest/handbook/doc",
        params={"path": "guide.md"},
        content=b"# Guide\nhello",
        headers={"content-type": "text/markdown"},
    )
    assert put.status_code == 201
    assert put.json()["extraction"]["status"] == "extracted"

    listed = client.get("/v1/fs/handbook/entries")
    assert "guide.md" in {e["path"] for e in listed.json()["items"]}

    read = client.get("/v1/fs/handbook/doc", params={"path": "guide.md"})
    assert read.json()["pages"][0]["text"] == "# Guide\nhello"

    assert client.delete("/v1/ingest/handbook/doc", params={"path": "guide.md"}).status_code == 202
    gone = client.get("/v1/fs/handbook/stat", params={"path": "guide.md"})
    assert gone.status_code == 404
