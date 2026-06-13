"""The store registry resolves builtins and rejects unknown backends."""

from __future__ import annotations

import pytest

from afs_core.contracts import ObjectStore
from afs_server.settings import Settings
from afs_server.stores import get_object_store
from afs_server.stores.objects_s3 import S3ObjectStore


def test_registry_builds_builtin_s3() -> None:
    store = get_object_store(Settings(object_store_backend="s3", data_bucket="b"))
    assert isinstance(store, S3ObjectStore)
    assert isinstance(store, ObjectStore)  # honours the contract


def test_registry_unknown_backend_raises() -> None:
    with pytest.raises(ValueError, match="unknown object store backend"):
        get_object_store(Settings(object_store_backend="does-not-exist"))
