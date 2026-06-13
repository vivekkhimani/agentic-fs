"""Ingestion write path. Scope: ingest."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from afs_core.models import CatalogEntry
from afs_server.dependencies import IngestDep, PrincipalDep

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


@router.put("/{namespace}/doc", response_model=CatalogEntry, status_code=status.HTTP_201_CREATED)
async def put_doc(
    namespace: str,
    request: Request,
    ingest: IngestDep,
    principal: PrincipalDep,
    path: Annotated[str, Query()],
) -> CatalogEntry:
    """Upload a document's bytes directly. Text-native files become readable at once."""
    data = await request.body()
    return await ingest.put_document(
        principal, namespace, path, data, content_type=request.headers.get("content-type")
    )


@router.delete("/{namespace}/doc", status_code=status.HTTP_202_ACCEPTED)
async def delete_doc(
    namespace: str,
    ingest: IngestDep,
    principal: PrincipalDep,
    path: Annotated[str, Query()],
) -> Response:
    await ingest.delete_document(principal, namespace, path)
    return Response(status_code=status.HTTP_202_ACCEPTED)
