"""Meta endpoints: liveness, readiness, whoami."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from afs_server import __version__
from afs_server.dependencies import CatalogDep, PrincipalDep
from afs_server.schemas import HealthResponse, MeResponse

router = APIRouter(prefix="/v1", tags=["meta"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness — does not touch dependencies."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/readyz", response_model=HealthResponse)
async def readyz(catalog: CatalogDep, response: Response) -> HealthResponse:
    """Readiness — confirms the catalog store is reachable."""
    try:
        await catalog.list_tenants(limit=1)
    except Exception:  # readiness reports degraded, never raises
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", version=__version__)
    return HealthResponse(status="ok", version=__version__)


@router.get("/me", response_model=MeResponse)
async def me(principal: PrincipalDep) -> MeResponse:
    return MeResponse(
        tenant_id=principal.tenant_id,
        principal_id=principal.principal_id,
        scopes=sorted(principal.scopes),
        namespaces=sorted(principal.namespaces) if principal.namespaces is not None else None,
    )
