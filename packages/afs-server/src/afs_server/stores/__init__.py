"""Store registry — the seam where a self-hoster swaps a backend.

The object store and the catalog store are each selected by a backend *name* from
settings. Builtins are wired here; third-party backends are discovered via an
entry-point group (``afs.object_stores`` / ``afs.catalog_stores``), so swapping in
your own is ``pip install`` + one env var — no fork:

    # in your package's pyproject.toml
    [project.entry-points."afs.object_stores"]
    myblob = "mypkg.store:build"          # build(settings) -> ObjectStore

    $ export AFS_OBJECT_STORE_BACKEND=myblob

See ``docs/swap-guides/``.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any

from afs_core.contracts import CatalogStore, ObjectStore
from afs_server.stores.catalog_dynamodb import DynamoDBCatalogStore
from afs_server.stores.objects_s3 import S3ObjectStore

if TYPE_CHECKING:
    from afs_server.settings import Settings

_OBJECT_STORE_ENTRY_GROUP = "afs.object_stores"
_CATALOG_STORE_ENTRY_GROUP = "afs.catalog_stores"

# Builtin factories: name -> (settings) -> store.
_OBJECT_STORE_BUILTINS: dict[str, Callable[[Settings], ObjectStore]] = {
    "s3": S3ObjectStore.from_settings,
}
_CATALOG_STORE_BUILTINS: dict[str, Callable[[Settings], CatalogStore]] = {
    "dynamodb": DynamoDBCatalogStore.from_settings,
}


def _resolve(
    name: str,
    builtins: dict[str, Callable[[Settings], Any]],
    group: str,
    settings: Settings,
    kind: str,
) -> Any:
    builtin = builtins.get(name)
    if builtin is not None:
        return builtin(settings)
    for ep in entry_points(group=group):
        if ep.name == name:
            return ep.load()(settings)
    available = sorted(builtins) + [ep.name for ep in entry_points(group=group)]
    raise ValueError(
        f"unknown {kind} backend {name!r}; available: {', '.join(available) or 'none'}"
    )


def get_object_store(settings: Settings) -> ObjectStore:
    """Build the configured ``ObjectStore`` (builtin or installed plugin)."""
    return _resolve(
        settings.object_store_backend,
        _OBJECT_STORE_BUILTINS,
        _OBJECT_STORE_ENTRY_GROUP,
        settings,
        "object store",
    )


def get_catalog_store(settings: Settings) -> CatalogStore:
    """Build the configured ``CatalogStore`` (builtin or installed plugin)."""
    return _resolve(
        settings.catalog_backend,
        _CATALOG_STORE_BUILTINS,
        _CATALOG_STORE_ENTRY_GROUP,
        settings,
        "catalog store",
    )


__all__ = ["get_catalog_store", "get_object_store"]
