"""S3 connector — certified against the afs-core kit using moto."""

from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from afs_connector_sdk.connectors.s3 import S3Connector
from afs_core.testing import ConnectorConformance


@pytest.fixture
def s3_source() -> Iterator[str]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="docs")
        client.put_object(Bucket="docs", Key="reports/a.md", Body=b"alpha")
        client.put_object(Bucket="docs", Key="reports/sub/b.txt", Body=b"beta beta")
        client.put_object(Bucket="docs", Key="reports/", Body=b"")  # folder placeholder
        yield "s3://docs/reports/"


class TestS3Connector(ConnectorConformance):
    @pytest.fixture
    def connector(self, s3_source: str) -> S3Connector:
        return S3Connector(s3_source, region="us-east-1")


def test_strips_prefix_and_skips_placeholders(s3_source: str) -> None:
    connector = S3Connector(s3_source, region="us-east-1")
    items = {item.path: item for item in connector.discover()}
    assert set(items) == {"a.md", "sub/b.txt"}
    assert connector.fetch(items["a.md"]) == b"alpha"
    assert items["a.md"].version  # ETag carried as the change token


def test_rejects_non_s3_source() -> None:
    with pytest.raises(ValueError, match="s3://bucket/prefix"):
        S3Connector("/local/path")
