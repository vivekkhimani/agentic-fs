"""ASGI application factory.

Assembles the REST surface, wires the configured stores at startup, and renders
every ``AfsError`` as an RFC 9457 ``application/problem+json`` envelope. The MCP
mount is added in a later slice on this same app (shared service layer, no HTTP
self-calls).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from afs_core.errors import AfsError
from afs_server import __version__
from afs_server.dependencies import get_settings
from afs_server.routers import fs, meta
from afs_server.stores import get_catalog_store, get_object_store

logger = logging.getLogger("afs_server")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.catalog = get_catalog_store(settings)
    app.state.objects = get_object_store(settings)
    logger.info(
        "afs-server %s started (object_store=%s, catalog=%s, auth=%s)",
        __version__,
        settings.object_store_backend,
        settings.catalog_backend,
        settings.auth_mode,
    )
    yield


async def _afs_error_handler(request: Request, exc: AfsError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_problem(instance=request.url.path),
        media_type="application/problem+json",
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="agentic-fs",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_exception_handler(AfsError, _afs_error_handler)  # type: ignore[arg-type]
    app.include_router(meta.router)
    app.include_router(fs.router)
    return app


app = create_app()
