"""The ``ObjectStore`` contract (plan §5.2).

Structural ``Protocol`` — adopters implement it without importing our hierarchy
or depending on ``afs-server``. S3 is the only production impl; the protocol
exists so MinIO/LocalStack back local dev and an in-memory fake backs tests.
Certify any impl with ``ObjectStoreConformance`` (afs_core.testing).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from afs_core.models import ObjectStat, Page, PresignedPut


@runtime_checkable
class ObjectStore(Protocol):
    async def get(self, key: str, *, start: int | None = None, end: int | None = None) -> bytes:
        """Fetch an object, optionally a byte range ``[start, end]`` (inclusive)."""
        ...

    async def put(
        self, key: str, body: bytes, *, content_type: str | None = None
    ) -> ObjectStat: ...

    async def delete(self, key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under ``prefix``; returns the count removed."""
        ...

    async def stat(self, key: str) -> ObjectStat | None:
        """Metadata for ``key``, or ``None`` if it does not exist."""
        ...

    async def list(
        self, prefix: str, *, cursor: str | None = None, limit: int = 1000
    ) -> Page[ObjectStat]: ...

    async def presigned_put(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int = 900
    ) -> PresignedPut: ...

    async def presigned_get(self, key: str, *, expires_in: int = 300) -> str: ...
