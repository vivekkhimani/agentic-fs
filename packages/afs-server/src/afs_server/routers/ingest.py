"""Ingestion write path. Scope: ingest."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response, status

from afs_core.models import CatalogEntry, SourceRef
from afs_server.dependencies import IngestDep, PrincipalDep

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


@router.put("/{namespace}/doc", response_model=CatalogEntry, status_code=status.HTTP_201_CREATED)
async def put_doc(
    namespace: str,
    request: Request,
    ingest: IngestDep,
    principal: PrincipalDep,
    path: Annotated[str, Query()],
    connector_id: Annotated[str | None, Header(alias="X-Afs-Connector-Id")] = None,
    remote_id: Annotated[str | None, Header(alias="X-Afs-Remote-Id")] = None,
    source_version: Annotated[str | None, Header(alias="X-Afs-Source-Version")] = None,
) -> CatalogEntry:
    """Upload a document's bytes directly. Text-native files become readable at once.

    A connector may stamp provenance via ``X-Afs-Connector-Id`` / ``-Remote-Id`` /
    ``-Source-Version`` headers; the version is what lets a later sync skip the
    fetch when nothing changed (ADR 0008).
    """
    data = await request.body()
    source = (
        SourceRef(connector_id=connector_id, remote_id=remote_id or path, version=source_version)
        if connector_id
        else None
    )
    return await ingest.put_document(
        principal,
        namespace,
        path,
        data,
        content_type=request.headers.get("content-type"),
        source=source,
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
