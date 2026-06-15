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
    files: list[str] = []  # populated instead of matches in files_with_matches mode
    files_searched: int
    truncated: bool  # a budget (files/matches/bytes) was hit — narrow the query


class TreeResponse(BaseModel):
    """An indented directory tree of a namespace (like ``ls -R``/``tree``)."""

    tree: str  # indented text; dirs end with "/"
    dirs: int
    files: int
    truncated: bool  # the entry cap was hit — narrow with a prefix


class FindItem(BaseModel):
    path: str
    size: int
    content_type: str
    status: str  # extraction status
    updated_at: str  # ISO-8601


class FindResponse(BaseModel):
    """Catalog entries matching a glob + metadata filters (the ``find`` to grep)."""

    items: list[FindItem]
    truncated: bool


class OutlineHeading(BaseModel):
    level: int  # 1-6 (markdown heading depth)
    title: str
    page: int  # 1-based derived page the heading is on


class OutlineResponse(BaseModel):
    """A document's structure — its markdown headings + page map (a symbol map)."""

    path: str
    page_count: int
    headings: list[OutlineHeading]
    truncated: bool  # heading cap or page cap hit


class Table(BaseModel):
    page: int  # 1-based derived page the table was found on
    header: list[str]
    rows: list[list[str]]


class TablesResponse(BaseModel):
    """Markdown tables parsed out of a document's extracted text."""

    path: str
    tables: list[Table]
    truncated: bool  # table/row cap or page cap hit


class DiffResponse(BaseModel):
    """A bounded unified diff between two documents' extracted text."""

    path_a: str
    path_b: str
    diff: str  # unified-diff text ("" when identical)
    truncated: bool  # the line budget was hit


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
