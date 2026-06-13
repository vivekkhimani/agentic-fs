"""Certify S3ObjectStore against the afs-core conformance kit, using moto.

Same kit that certifies the in-memory fake — one contract, every backend proven
the same way. Local integration against real MinIO/R2 is an endpoint_url swap.
"""

from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from afs_core.testing import ObjectStoreConformance
from afs_server.stores.objects_s3 import S3ObjectStore

_BUCKET = "test-bucket"


class TestS3ObjectStore(ObjectStoreConformance):
    @pytest.fixture
    def store(self) -> Iterator[S3ObjectStore]:
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=_BUCKET)
            yield S3ObjectStore(bucket=_BUCKET, region="us-east-1")
