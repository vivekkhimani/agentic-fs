"""Async HTTP client for the agentic-fs ingest + read API.

Signing is done by building the httpx request first, then signing its *final*
URL and attaching the result — so the bytes signed are exactly the bytes sent.
That avoids the SigV4 query-encoding mismatch you hit when the signed URL and
the transmitted URL disagree on how a path like ``a/b.md`` is escaped.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from afs_connector_sdk.auth import NoAuth, RequestSigner


class IngestClient:
    def __init__(
        self, base_url: str, *, signer: RequestSigner | None = None, timeout: float = 30.0
    ) -> None:
        self._base = base_url.rstrip("/")
        self._signer = signer or NoAuth()
        self._http = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> IngestClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        request = self._http.build_request(
            method, f"{self._base}{path}", params=params, content=content, headers=headers
        )
        request.headers.update(
            self._signer.headers_for(
                method=request.method, url=str(request.url), body=content or b""
            )
        )
        return await self._http.send(request)

    async def put_document(
        self, namespace: str, path: str, data: bytes, *, content_type: str | None = None
    ) -> dict[str, Any]:
        resp = await self._send(
            "PUT",
            f"/v1/ingest/{namespace}/doc",
            params={"path": path},
            content=data,
            content_type=content_type,
        )
        resp.raise_for_status()
        return resp.json()

    async def stat(self, namespace: str, path: str) -> dict[str, Any] | None:
        resp = await self._send("GET", f"/v1/fs/{namespace}/stat", params={"path": path})
        if resp.status_code == httpx.codes.NOT_FOUND:
            return None
        resp.raise_for_status()
        return resp.json()

    async def delete_document(self, namespace: str, path: str) -> None:
        resp = await self._send("DELETE", f"/v1/ingest/{namespace}/doc", params={"path": path})
        if resp.status_code not in (200, 202, 204):
            resp.raise_for_status()

    async def list_paths(self, namespace: str, prefix: str = "") -> list[str]:
        paths: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"prefix": prefix, "limit": 200}
            if cursor:
                params["cursor"] = cursor
            resp = await self._send("GET", f"/v1/fs/{namespace}/entries", params=params)
            resp.raise_for_status()
            page = resp.json()
            paths.extend(entry["path"] for entry in page.get("items", []))
            cursor = page.get("next_cursor")
            if not cursor:
                return paths
