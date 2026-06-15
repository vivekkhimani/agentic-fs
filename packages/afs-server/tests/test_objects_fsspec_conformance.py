"""Certify FsspecObjectStore against the same kit that certifies S3 + the fake.

Runs over a temp ``file://`` filesystem (real fsspec LocalFileSystem) — proving
the adapter satisfies the ObjectStore contract end to end. Skipped if the
``[fsspec]`` extra isn't installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fsspec")

from afs_core.testing.conformance import ObjectStoreConformance
from afs_server.stores.objects_fsspec import FsspecObjectStore


class TestFsspecObjectStoreConformance(ObjectStoreConformance):
    @pytest.fixture
    def store(self, tmp_path) -> FsspecObjectStore:
        return FsspecObjectStore(root=f"file://{tmp_path}")


def test_from_settings_requires_root() -> None:
    from afs_server.settings import Settings

    with pytest.raises(ValueError, match="AFS_FSSPEC_ROOT"):
        FsspecObjectStore.from_settings(Settings(object_store_backend="fsspec"))


async def test_memory_filesystem_roundtrip() -> None:
    # A different backend (memory://) to show the adapter is fs-agnostic.
    store = FsspecObjectStore(root="memory://afs-mem-test")
    await store.put("a/b.txt", b"hi", content_type="text/plain")
    assert await store.get("a/b.txt") == b"hi"
    assert (await store.stat("a/b.txt")).size == 2
    assert [o.key for o in (await store.list("a/")).items] == ["a/b.txt"]
    await store.delete("a/b.txt")
    assert await store.stat("a/b.txt") is None
