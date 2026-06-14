"""Response schemas for the REST surface (snake_case wire format, bounded outputs)."""

from __future__ import annotations

from pydantic import BaseModel

from afs_core.models import CatalogEntry, Page


class HealthResponse(BaseModel):
    status: str
    version: str


class MeResponse(BaseModel):
    tenant_id: str
    principal_id: str
    scopes: list[str]
    namespaces: list[str] | None  # None = all namespaces in the tenant


# Listing reuses the generic catalog page.
EntryPage = Page[CatalogEntry]


class ReadPage(BaseModel):
    page: int
    text: str


class ReadResponse(BaseModel):
    """A bounded, page-ranged read of a document's extracted text."""

    path: str
    pages: list[ReadPage]
    page_count: int
    range: tuple[int, int]
    truncated: bool


class GlobResponse(BaseModel):
    """Catalog paths matching a glob pattern."""

    paths: list[str]
    next_cursor: str | None = None


class GrepMatch(BaseModel):
    path: str
    page: int  # 1-based derived page
    line: int  # 1-based line within the page
    text: str  # the matching line (length-capped)
    before: list[str] = []  # context lines (when requested)
    after: list[str] = []


class GrepResponse(BaseModel):
    """Bounded two-stage grep results over a namespace's derived text."""

    matches: list[GrepMatch]
    files_searched: int
    truncated: bool  # a budget (files/matches/bytes) was hit — narrow the query


class ScratchWriteResult(BaseModel):
    """Result of a scratch write/delete, with the principal's quota usage after."""

    path: str
    bytes: int  # bytes written (0 for delete)
    bytes_used: int
    objects_used: int


class ScratchReadResult(BaseModel):
    path: str
    content: str


class ScratchListResult(BaseModel):
    paths: list[str]
