"""Store registry — the seam where a self-hoster swaps a backend.

An ``ObjectStore`` (and, in a later slice, a ``CatalogStore``) is selected by a
backend *name* from settings. Builtins are wired here; third-party backends are
discovered via the ``afs.object_stores`` entry-point group, so swapping in your
own is ``pip install`` + one env var — no fork:

    # in your package's pyproject.toml
    [project.entry-points."afs.object_stores"]
    myblob = "mypkg.store:build"          # build(settings) -> ObjectStore

    $ export AFS_OBJECT_STORE_BACKEND=myblob

See ``docs/swap-guides/object-store.md``.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from afs_core.contracts import ObjectStore
from afs_server.stores.objects_s3 import S3ObjectStore

if TYPE_CHECKING:
    from afs_server.settings import Settings

_OBJECT_STORE_ENTRY_GROUP = "afs.object_stores"

# Builtin object-store factories: name -> (settings) -> ObjectStore.
_OBJECT_STORE_BUILTINS = {
    "s3": S3ObjectStore.from_settings,
}


def get_object_store(settings: Settings) -> ObjectStore:
    """Build the configured ``ObjectStore`` (builtin or installed plugin)."""
    name = settings.object_store_backend
    builtin = _OBJECT_STORE_BUILTINS.get(name)
    if builtin is not None:
        return builtin(settings)

    for ep in entry_points(group=_OBJECT_STORE_ENTRY_GROUP):
        if ep.name == name:
            return ep.load()(settings)

    available = sorted(_OBJECT_STORE_BUILTINS) + [
        ep.name for ep in entry_points(group=_OBJECT_STORE_ENTRY_GROUP)
    ]
    raise ValueError(
        f"unknown object store backend {name!r}; available: {', '.join(available) or 'none'}"
    )


__all__ = ["get_object_store"]
