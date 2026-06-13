"""The store registry resolves builtins and rejects unknown backends."""

from __future__ import annotations

import pytest

from afs_core.contracts import CatalogStore, ObjectStore
from afs_server.settings import Settings
from afs_server.stores import get_catalog_store, get_object_store
from afs_server.stores.catalog_dynamodb import DynamoDBCatalogStore
from afs_server.stores.objects_s3 import S3ObjectStore


def test_registry_builds_builtin_s3() -> None:
    store = get_object_store(Settings(object_store_backend="s3", data_bucket="b"))
    assert isinstance(store, S3ObjectStore)
    assert isinstance(store, ObjectStore)  # honours the contract


def test_registry_builds_builtin_dynamodb() -> None:
    store = get_catalog_store(Settings(catalog_backend="dynamodb", catalog_table="t"))
    assert isinstance(store, DynamoDBCatalogStore)
    assert isinstance(store, CatalogStore)


def test_registry_unknown_object_backend_raises() -> None:
    with pytest.raises(ValueError, match="unknown object store backend"):
        get_object_store(Settings(object_store_backend="does-not-exist"))


def test_registry_unknown_catalog_backend_raises() -> None:
    with pytest.raises(ValueError, match="unknown catalog store backend"):
        get_catalog_store(Settings(catalog_backend="does-not-exist"))
