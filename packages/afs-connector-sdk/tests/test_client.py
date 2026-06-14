"""IngestClient HTTP behavior + the sign-the-final-URL property (via MockTransport)."""

from __future__ import annotations

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
