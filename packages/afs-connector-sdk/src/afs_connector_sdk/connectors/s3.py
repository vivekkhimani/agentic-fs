"""S3 connector — crawl an ``s3://bucket/prefix`` of documents.

Source-side auth is the standard boto3 chain (env / profile / role), so reading
from S3 needs no special handling here — that's the connector pattern: each
source owns its own auth. Needs the ``[aws]`` extra (boto3).

Pass a prefix ending in ``/`` for folder semantics (``s3://bucket/docs/``); the
prefix is stripped from each key to form the agentic-fs path.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from afs_core.models import SourceItem


class S3Connector:
    name = "s3"

    def __init__(
        self, source: str, *, endpoint_url: str | None = None, region: str | None = None
    ) -> None:
        parsed = urlparse(source)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise ValueError(f"source must be s3://bucket/prefix, got {source!r}")
        self._bucket = parsed.netloc
        self._prefix = parsed.path.lstrip("/")
        try:
            import boto3
        except ModuleNotFoundError as err:  # pragma: no cover - import guard
            raise RuntimeError(
                "the s3 connector needs the optional extra: pip install 'afs-connector-sdk[aws]'"
            ) from err
        self._s3: Any = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def discover(self) -> Iterator[SourceItem]:
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue  # skip "folder" placeholder objects
                rel = key[len(self._prefix) :] if self._prefix else key
                rel = rel.lstrip("/")
                if not rel:
                    continue
                yield SourceItem(
                    path=rel,
                    locator=key,
                    size=obj.get("Size"),
                    version=(obj.get("ETag") or "").strip('"') or None,
                )

    def fetch(self, item: SourceItem) -> bytes:
        resp = self._s3.get_object(Bucket=self._bucket, Key=item.locator)
        return resp["Body"].read()
