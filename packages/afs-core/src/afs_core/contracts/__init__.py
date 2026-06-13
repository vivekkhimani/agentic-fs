"""The agentic-fs contracts: async ``typing.Protocol`` interfaces (plan §5).

Structural — adopters implement without importing our hierarchy. Each is proven
by a conformance kit in :mod:`afs_core.testing`.
"""

from afs_core.contracts.catalog import CatalogStore
from afs_core.contracts.normalize import NormalizationError, Normalizer
from afs_core.contracts.objects import ObjectStore

__all__ = ["CatalogStore", "NormalizationError", "Normalizer", "ObjectStore"]
