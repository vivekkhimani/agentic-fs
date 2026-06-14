"""Connector registry — builtins + the ``afs.connectors`` entry-point group.

Same pattern as the store and normalizer registries: pick a connector by name.
Third-party connectors (Google Drive, SharePoint, …) register an entry point
whose value is a callable ``(source, **options) -> Connector``; they need no
change here.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from afs_core.contracts import Connector

_ENTRY_GROUP = "afs.connectors"


def _builtins() -> dict[str, object]:
    # Imported lazily so a connector's optional deps (boto3 for s3) aren't needed
    # just to load the registry or use a different connector.
    from afs_connector_sdk.connectors.local import LocalConnector
    from afs_connector_sdk.connectors.s3 import S3Connector

    return {"local": LocalConnector, "s3": S3Connector}


def build_connector(name: str, source: str, **options: str) -> Connector:
    """Construct a connector by name over ``source`` (with connector-specific options)."""
    factory = _builtins().get(name)
    if factory is None:
        for ep in entry_points(group=_ENTRY_GROUP):
            if ep.name == name:
                factory = ep.load()
                break
    if factory is None:
        available = sorted(_builtins()) + [ep.name for ep in entry_points(group=_ENTRY_GROUP)]
        raise ValueError(f"unknown connector {name!r}; available: {', '.join(available)}")
    return factory(source, **options)  # type: ignore[operator]
