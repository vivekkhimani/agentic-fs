"""Service layer — business logic shared in-process by REST routes and (later) MCP tools."""

from afs_server.services.fs import FsService

__all__ = ["FsService"]
