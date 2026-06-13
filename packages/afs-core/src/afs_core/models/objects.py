"""Object-store DTOs (plan §5.2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ObjectStat(BaseModel):
    """Metadata for one stored object."""

    key: str
    size: int
    etag: str
    content_type: str | None = None
    last_modified: datetime | None = None


class PresignedPut(BaseModel):
    """A presigned upload intent — the server builds the key; the client never does."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime
    max_bytes: int
