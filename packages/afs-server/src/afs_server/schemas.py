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
