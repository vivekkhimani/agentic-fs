"""Conformance kits + in-memory fakes (plan §5).

Adopters import the conformance kit, subclass it, point the ``store`` fixture at
their implementation, and make it green. The in-memory fakes are the reference
impls and back afs-core's own tests.
"""

from afs_core.testing.conformance import (
    CatalogStoreConformance,
    ConnectorConformance,
    NormalizerConformance,
    ObjectStoreConformance,
    make_entry,
)
from afs_core.testing.memory import InMemoryCatalogStore, InMemoryObjectStore

__all__ = [
    "CatalogStoreConformance",
    "ConnectorConformance",
    "InMemoryCatalogStore",
    "InMemoryObjectStore",
    "NormalizerConformance",
    "ObjectStoreConformance",
    "make_entry",
]
