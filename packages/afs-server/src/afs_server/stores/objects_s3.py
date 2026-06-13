"""S3 implementation of the ``ObjectStore`` contract (plan §5.2).

Uses sync boto3 wrapped in ``asyncio.to_thread`` — see
``docs/decisions/0001-boto3-sync-to-thread.md``: it's moto-testable, simple, and
fine for the request-scoped serving model.

S3-compatible by construction: point ``endpoint_url`` at MinIO, Cloudflare R2,
Wasabi, or Backblaze B2 and this same class is your object store with no code
change (``docs/swap-guides/object-store.md``).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import boto3
from botocore.exceptions import ClientError

from afs_core.errors import NotFoundError
from afs_core.models import ObjectStat, Page, PresignedPut

if TYPE_CHECKING:
    from afs_server.settings import Settings

_NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}


class S3ObjectStore:
    """``ObjectStore`` backed by S3 (or any S3-compatible endpoint)."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        kms_key_arn: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._kms_key_arn = kms_key_arn
        self._region = region
        self._endpoint_url = endpoint_url
        self._client_cache: Any = None

    @property
    def _client(self) -> Any:
        # Lazy: don't create a client (and resolve credentials) at construction —
        # so building the store is side-effect-free and the registry can wire it
        # without AWS credentials present.
        if self._client_cache is None:
            self._client_cache = boto3.client(
                "s3", region_name=self._region, endpoint_url=self._endpoint_url
            )
        return self._client_cache

    @classmethod
    def from_settings(cls, settings: Settings) -> S3ObjectStore:
        return cls(
            bucket=settings.data_bucket,
            region=settings.region,
            endpoint_url=settings.s3_endpoint_url,
            kms_key_arn=settings.kms_key_arn,
        )

    def _encryption_args(self) -> dict[str, str]:
        if self._kms_key_arn:
            return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self._kms_key_arn}
        return {}

    @staticmethod
    def _is_not_found(err: ClientError) -> bool:
        return err.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES

    async def get(self, key: str, *, start: int | None = None, end: int | None = None) -> bytes:
        rng: str | None = None
        if start is not None or end is not None:
            rng = f"bytes={start or 0}-" + ("" if end is None else str(end))

        def _get() -> bytes:
            kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
            if rng is not None:
                kwargs["Range"] = rng
            try:
                resp = self._client.get_object(**kwargs)
            except ClientError as err:
                if self._is_not_found(err):
                    raise NotFoundError("object not found", detail={"key": key}) from err
                raise
            return resp["Body"].read()

        return await asyncio.to_thread(_get)

    async def put(self, key: str, body: bytes, *, content_type: str | None = None) -> ObjectStat:
        def _put() -> ObjectStat:
            kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": key, "Body": body}
            if content_type:
                kwargs["ContentType"] = content_type
            kwargs.update(self._encryption_args())
            resp = self._client.put_object(**kwargs)
            return ObjectStat(
                key=key,
                size=len(body),
                etag=resp["ETag"].strip('"'),
                content_type=content_type,
                last_modified=datetime.now(UTC),
            )

        return await asyncio.to_thread(_put)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        def _delete_prefix() -> int:
            paginator = self._client.get_paginator("list_objects_v2")
            removed = 0
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                batch = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if batch:
                    self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": batch})
                    removed += len(batch)
            return removed

        return await asyncio.to_thread(_delete_prefix)

    async def stat(self, key: str) -> ObjectStat | None:
        def _stat() -> ObjectStat | None:
            try:
                resp = self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as err:
                if self._is_not_found(err):
                    return None
                raise
            return ObjectStat(
                key=key,
                size=resp["ContentLength"],
                etag=resp["ETag"].strip('"'),
                content_type=resp.get("ContentType"),
                last_modified=resp.get("LastModified"),
            )

        return await asyncio.to_thread(_stat)

    async def list(
        self, prefix: str, *, cursor: str | None = None, limit: int = 1000
    ) -> Page[ObjectStat]:
        def _list() -> Page[ObjectStat]:
            kwargs: dict[str, Any] = {
                "Bucket": self._bucket,
                "Prefix": prefix,
                "MaxKeys": limit,
            }
            if cursor:
                kwargs["ContinuationToken"] = cursor
            resp = self._client.list_objects_v2(**kwargs)
            items = [
                ObjectStat(
                    key=obj["Key"],
                    size=obj["Size"],
                    etag=obj["ETag"].strip('"'),
                    last_modified=obj.get("LastModified"),
                )
                for obj in resp.get("Contents", [])
            ]
            return Page(items=items, next_cursor=resp.get("NextContinuationToken"))

        return await asyncio.to_thread(_list)

    async def presigned_put(
        self, key: str, *, content_type: str, max_bytes: int, expires_in: int = 900
    ) -> PresignedPut:
        def _presign() -> PresignedPut:
            params: dict[str, Any] = {
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            }
            params.update(self._encryption_args())
            url = self._client.generate_presigned_url(
                "put_object", Params=params, ExpiresIn=expires_in
            )
            headers = {"Content-Type": content_type}
            if self._kms_key_arn:
                headers["x-amz-server-side-encryption"] = "aws:kms"
            return PresignedPut(
                url=url,
                headers=headers,
                expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
                max_bytes=max_bytes,
            )

        return await asyncio.to_thread(_presign)

    async def presigned_get(self, key: str, *, expires_in: int = 300) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
