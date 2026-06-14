"""Connector checkpoints — server-side sync cursors (ADR 0008). Scope: ingest.

Checkpoints live server-side so the corpus is self-describing: any runner of a
connector resumes from the same cursor. Backed by the catalog's
``get_checkpoint`` / ``put_checkpoint``.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from afs_core.models import SyncCheckpoint
from afs_server.dependencies import CatalogDep, PrincipalDep

router = APIRouter(prefix="/v1/connectors", tags=["connectors"])


@router.get("/{connector_id}/checkpoint", response_model=SyncCheckpoint | None)
async def get_checkpoint(
    connector_id: str, catalog: CatalogDep, principal: PrincipalDep
) -> SyncCheckpoint | None:
    principal.require_scope("ingest")
    return await catalog.get_checkpoint(principal.tenant_id, connector_id)


@router.put("/{connector_id}/checkpoint", status_code=status.HTTP_204_NO_CONTENT)
async def put_checkpoint(
    connector_id: str,
    checkpoint: SyncCheckpoint,
    catalog: CatalogDep,
    principal: PrincipalDep,
) -> Response:
    principal.require_scope("ingest")
    # The path is authoritative for the storage key.
    checkpoint = checkpoint.model_copy(update={"connector_id": connector_id})
    await catalog.put_checkpoint(principal.tenant_id, connector_id, checkpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
