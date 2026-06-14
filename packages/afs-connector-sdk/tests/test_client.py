"""IngestClient HTTP behavior + the sign-the-final-URL property (via MockTransport)."""

from __future__ import annotations

import json

import httpx

from afs_connector_sdk.client import IngestClient


class _CaptureSigner:
    def __init__(self) -> None:
        self.signed_urls: list[str] = []

    def headers_for(self, *, method: str, url: str, body: bytes) -> dict[str, str]:
        self.signed_urls.append(url)
        return {"authorization": "SIGNED"}


def _client_with(handler, signer=None) -> IngestClient:
    client = IngestClient("http://api.test", signer=signer)
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


async def test_put_signs_the_exact_url_it_sends() -> None:
    sent: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["url"] = str(request.url)
        sent["auth"] = request.headers.get("authorization", "")
        sent["ctype"] = request.headers.get("content-type", "")
        return httpx.Response(201, json={"path": "a/b.md", "checksum": "abc"})

    signer = _CaptureSigner()
    client = _client_with(handler, signer)
    entry = await client.put_document("ns", "a/b.md", b"hello", content_type="text/markdown")
    await client.aclose()

    assert entry["checksum"] == "abc"
    assert sent["auth"] == "SIGNED"
    assert sent["ctype"] == "text/markdown"
    # The signer must see the byte-identical URL the transport sent (no
    # re-encoding between signing and sending) — the crux of SigV4 over query paths.
    assert signer.signed_urls == [sent["url"]]


async def test_stat_404_is_none() -> None:
    client = _client_with(lambda req: httpx.Response(404, json={"detail": "nope"}))
    assert await client.stat("ns", "missing.md") is None
    await client.aclose()


async def test_list_paths_follows_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "c1":
            return httpx.Response(200, json={"items": [{"path": "b.md"}], "next_cursor": None})
        return httpx.Response(200, json={"items": [{"path": "a.md"}], "next_cursor": "c1"})

    client = _client_with(handler)
    assert await client.list_paths("ns") == ["a.md", "b.md"]
    await client.aclose()


async def test_no_auth_adds_no_authorization_header() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(202)

    client = _client_with(handler)  # default NoAuth
    await client.delete_document("ns", "a.md")
    await client.aclose()
    assert seen["auth"] is None


async def test_put_document_sends_provenance_headers() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cid"] = request.headers.get("x-afs-connector-id")
        seen["rid"] = request.headers.get("x-afs-remote-id")
        seen["ver"] = request.headers.get("x-afs-source-version")
        return httpx.Response(201, json={"checksum": "x"})

    client = _client_with(handler)
    await client.put_document(
        "ns", "a.md", b"hi", connector_id="local", remote_id="/abs/a.md", source_version="v1"
    )
    await client.aclose()
    assert (seen["cid"], seen["rid"], seen["ver"]) == ("local", "/abs/a.md", "v1")


async def test_get_checkpoint_handles_null_and_value() -> None:
    # The server returns JSON `null` when no checkpoint exists.
    null_client = _client_with(
        lambda req: httpx.Response(
            200, content=b"null", headers={"content-type": "application/json"}
        )
    )
    assert await null_client.get_checkpoint("local") is None
    await null_client.aclose()

    val_client = _client_with(
        lambda req: httpx.Response(200, json={"connector_id": "local", "cursor": "c7"})
    )
    assert await val_client.get_checkpoint("local") == "c7"
    await val_client.aclose()


async def test_put_checkpoint_posts_cursor() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(204)

    client = _client_with(handler)
    await client.put_checkpoint("local", "c9")
    await client.aclose()
    assert str(seen["url"]).endswith("/v1/connectors/local/checkpoint")
    assert seen["body"] == {"connector_id": "local", "cursor": "c9"}
