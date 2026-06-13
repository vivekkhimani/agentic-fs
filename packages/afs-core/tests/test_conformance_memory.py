"""Certify the in-memory fakes against the conformance kits.

Each real backend (DynamoDB, S3, Postgres) will add a parallel module that
subclasses the same kit — proving every impl honours one contract.
"""

from __future__ import annotations

import pytest

from afs_core.testing import (
    CatalogStoreConformance,
    InMemoryCatalogStore,
    InMemoryObjectStore,
    ObjectStoreConformance,
)


class TestInMemoryObjectStore(ObjectStoreConformance):
    @pytest.fixture
    def store(self) -> InMemoryObjectStore:
        return InMemoryObjectStore()


class TestInMemoryCatalogStore(CatalogStoreConformance):
    @pytest.fixture
    def store(self) -> InMemoryCatalogStore:
        return InMemoryCatalogStore()
