"""Certify DynamoDBCatalogStore against the afs-core conformance kit, using moto.

The moto table mirrors the schema the `catalog_dynamodb` Terraform module
provisions (PK/SK + the three GSIs), so the test exercises the real key mapping.
"""

from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from moto import mock_aws

from afs_core.testing import CatalogStoreConformance
from afs_server.stores.catalog_dynamodb import DynamoDBCatalogStore

_TABLE = "test-catalog"


def _create_table(client: object) -> None:
    client.create_table(  # type: ignore[attr-defined]
        TableName=_TABLE,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI2PK", "AttributeType": "S"},
            {"AttributeName": "GSI3PK", "AttributeType": "S"},
            {"AttributeName": "GSI3SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "gsi1_by_doc",
                "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi2_by_checksum",
                "KeySchema": [{"AttributeName": "GSI2PK", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "gsi3_by_extraction_status",
                "KeySchema": [
                    {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI3SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )


class TestDynamoDBCatalogStore(CatalogStoreConformance):
    @pytest.fixture
    def store(self) -> Iterator[DynamoDBCatalogStore]:
        with mock_aws():
            _create_table(boto3.client("dynamodb", region_name="us-east-1"))
            yield DynamoDBCatalogStore(table_name=_TABLE, region="us-east-1")
