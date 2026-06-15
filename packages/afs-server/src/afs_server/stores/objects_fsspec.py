"""fsspec implementation of the ``ObjectStore`` contract (ADR 0014).

One adapter over [fsspec](https://filesystem-spec.readthedocs.io) certifies the
store contract against **GCS, Azure Blob, HDFS, local disk, memory, and many more**
— broadening "bring your own storage" past the S3-compatible set without a
per-backend store. Pick it with ``AFS_OBJECT_STORE_BACKEND=fsspec`` and point
``AFS_FSSPEC_ROOT`` at an fsspec URL (``gcs://bucket/prefix``,
``az://container/prefix``, ``file:///var/lib/agentic-fs``); install the matching
fsspec backend (``gcsfs``/``adlfs``/…) alongside the ``[fsspec]`` extra.

fsspec's filesystem API is synchronous, so calls are wrapped in
``asyncio.to_thread`` (same model as the S3 store, [ADR 0001]). Object keys are
relative to the configured root.

Caveat: presigning is backend-dependent. Where the backend supports it (S3/GCS/AZ
via ``fs.sign``) we return a signed URL; otherwise we return the object's fsspec
URL and callers should use the server-side ``put``/``get`` path instead.
"""

from __future__ import annotations

import asyncio
import bisect
import contextlib
import hashlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from afs_core.errors import NotFoundError
from afs_core.models import ObjectStat, Page, PresignedPut

if TYPE_CHECKING:
    from afs_server.settings import Settings


def _mtime(info: dict[str, Any]) -> datetime | None:
    raw = info.get("LastModified") or info.get("last_modified")
    if isinstance(raw, datetime):
        return raw
    mtime = info.get("mtime")
    if isinstance(mtime, (int, float)):
        return datetime.fromtimestamp(mtime, UTC)
    return None


class FsspecObjectStore:
    """``ObjectStore`` backed by any fsspec filesystem."""

    def __init__(self, *, root: str, storage_options: dict[str, Any] | None = None) -> None:
        import fsspec

        # url_to_fs resolves the protocol + the path within it; keys hang off `base`.
        self._fs, base = fsspec.core.url_to_fs(root, **(storage_options or {}))
        self._base = base.rstrip("/")

    @classmethod
    def from_settings(cls, settings: Settings) -> FsspecObjectStore:
        if not settings.fsspec_root:
            raise ValueError(
                "object_store_backend='fsspec' requires AFS_FSSPEC_ROOT "
                "(e.g. gcs://bucket/prefix, az://container/prefix, file:///var/lib/agentic-fs)"
            )
        return cls(root=settings.fsspec_root)

    def _full(self, key: str) -> str:
        return f"{self._base}/{key}" if self._base else key

    def _strip(self, full: str) -> str:
        if self._base and full.startswith(self._base + "/"):
            return full[len(self._base) + 1 :]
        return full.lstrip("/")

    async def get(self, key: str, *, start: int | None = None, end: int | None = None) -> bytes:
        def _get() -> bytes:
            try:
                return self._fs.cat_file(
                    self._full(key),
                    start=start,
                    end=None if end is None else end + 1,  # contract end is inclusive
                )
            except FileNotFoundError as err:
                raise NotFoundError("object not found", detail={"key": key}) from err

        return await asyncio.to_thread(_get)

    async def put(self, key: str, body: bytes, *, content_type: str | None = None) -> ObjectStat:
        def _put() -> ObjectStat:
            full = self._full(key)
            parent = full.rsplit("/", 1)[0] if "/" in full else ""
            if parent:
                with contextlib.suppress(FileExistsError, NotImplementedError):
                    self._fs.makedirs(parent, exist_ok=True)
            self._fs.pipe_file(full, body)
            return ObjectStat(
                key=key,
                size=len(body),
                etag=hashlib.md5(body).hexdigest(),  # an etag, not a security hash
                content_type=content_type,
                last_modified=datetime.now(UTC),
            )

        return await asyncio.to_thread(_put)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            with contextlib.suppress(FileNotFoundError):  # idempotent, like S3
                self._fs.rm_file(self._full(key))

        await asyncio.to_thread(_delete)

    async def delete_prefix(self, prefix: str) -> int:
        def _delete_prefix() -> int:
            root = self._full(prefix).rstrip("/")
            try:
                found = self._fs.find(root)
            except FileNotFoundError:
                return 0
            keys = [f for f in found if self._strip(f).startswith(prefix)]
            for full in keys:
                with contextlib.suppress(FileNotFoundError):
                    self._fs.rm_file(full)
            return len(keys)

        return await asyncio.to_thread(_delete_prefix)

    async def stat(self, key: str) -> ObjectStat | None:
        def _stat() -> ObjectStat | None:
            try:
                info = self._fs.info(self._full(key))
            except FileNotFoundError:
                return None
            return ObjectStat(
                key=key,
                size=int(info.get("size") or 0),
                etag=str(info.get("ETag", "")).strip('"'),
                content_type=info.get("ContentType"),
                last_modified=_mtime(info),
            )

        return await asyncio.to_thread(_stat)

    async def list(
        self, prefix: str, *, cursor: str | None = None, limit: int = 1000
    ) -> Page[ObjectStat]:
        def _list() -> Page[ObjectStat]:
            slash = prefix.rfind("/")
            search = self._full(prefix[: slash + 1] if slash >= 0 else "").rstrip("/")
            try:
                found = self._fs.find(search, detail=True)
            except FileNotFoundError:
                return Page(items=[], next_cursor=None)
            infos = {
                k: info
                for full, info in found.items()
                if (k := self._strip(full)).startswith(prefix)
            }
            keys = sorted(infos)
            offset = bisect.bisect_right(keys, cursor) if cursor else 0
            window = keys[offset : offset + limit]
            has_more = offset + limit < len(keys)
            items = [
                ObjectStat(
                    key=k,
                    size=int(infos[k].get("size") or 0),
                    etag=str(infos[k].get("ETag", "")).strip('"'),
                    last_modified=_mtime(infos[k]),
                )
                for k in window
            ]
            return Page(items=items, next_cursor=window[-1] if (has_more and window) else None)

        return await asyncio.to_thread(_list)

    def _signed_url(self, key: str, expires_in: int) -> str:
        full = self._full(key)
        try:
            return self._fs.sign(full, expiration=expires_in)
        except (NotImplementedError, ValueError):
            return self._fs.unstrip_protocol(full)  # plain object URL (no native presign)

    async def presigned_put(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int = 900
    ) -> PresignedPut:
        def _presign() -> PresignedPut:
            return PresignedPut(
                url=self._signed_url(key, expires_in),
                headers={"Content-Type": content_type},
                expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
                max_bytes=max_bytes,
            )

        return await asyncio.to_thread(_presign)

    async def presigned_get(self, key: str, *, expires_in: int = 300) -> str:
        return await asyncio.to_thread(self._signed_url, key, expires_in)
