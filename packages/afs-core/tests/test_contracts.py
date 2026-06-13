"""The fakes structurally satisfy the runtime-checkable Protocols."""

from __future__ import annotations

from afs_core.contracts import CatalogStore, ObjectStore
from afs_core.testing import InMemoryCatalogStore, InMemoryObjectStore


def test_in_memory_object_store_satisfies_protocol() -> None:
    assert isinstance(InMemoryObjectStore(), ObjectStore)


def test_in_memory_catalog_store_satisfies_protocol() -> None:
    assert isinstance(InMemoryCatalogStore(), CatalogStore)
