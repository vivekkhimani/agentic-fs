"""ASGI application factory.

Assembles the REST surface + the MCP mount (sharing one ``FsService`` in-process,
no HTTP self-calls), wires the configured stores, and renders every ``AfsError``
as an RFC 9457 ``application/problem+json`` envelope.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from afs_core.errors import AfsError
from afs_server import __version__
from afs_server.extraction import build_pipeline
from afs_server.mcp import build_mcp
from afs_server.routers import fs, ingest, meta
from afs_server.services import FsService
from afs_server.settings import load_settings
from afs_server.stores import get_catalog_store, get_object_store

logger = logging.getLogger("afs_server")


async def _afs_error_handler(request: Request, exc: AfsError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_problem(instance=request.url.path),
        media_type="application/problem+json",
    )


def create_app() -> FastAPI:
    settings = load_settings()
    # Stores are lazy (no I/O / credentials at construction), so we can build the
    # service + MCP server now and share the service between REST and MCP.
    catalog = get_catalog_store(settings)
    objects = get_object_store(settings)
    fs_service = FsService(catalog, objects)
    extraction_pipeline = build_pipeline(settings.extraction_ladder_names)

    mcp_app = build_mcp(fs_service, settings).http_app(path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.catalog = catalog
        app.state.objects = objects
        app.state.extraction_pipeline = extraction_pipeline
        logger.info(
            "afs-server %s started (object_store=%s, catalog=%s, auth=%s)",
            __version__,
            settings.object_store_backend,
            settings.catalog_backend,
            settings.auth_mode,
        )
        # The MCP session manager runs under its own lifespan — nest it so the
        # mounted /mcp app works (Starlette does not propagate sub-app lifespans).
        async with mcp_app.lifespan(app):
            yield

    app = FastAPI(title="agentic-fs", version=__version__, lifespan=lifespan)
    app.add_exception_handler(AfsError, _afs_error_handler)  # type: ignore[arg-type]
    app.include_router(meta.router)
    app.include_router(fs.router)
    app.include_router(ingest.router)
    app.mount("/mcp", mcp_app)
    return app


app = create_app()
