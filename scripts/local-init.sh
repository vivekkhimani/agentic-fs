#!/bin/sh
# Create the local S3 bucket (MinIO) and DynamoDB table (DynamoDB Local) that the
# api container expects. Idempotent — safe to re-run. Used by docker-compose.
set -e

export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-local}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-local}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

S3_ENDPOINT="${S3_ENDPOINT:-http://minio:9000}"
DDB_ENDPOINT="${DDB_ENDPOINT:-http://dynamodb:8000}"

echo "creating S3 bucket agentic-fs-data on ${S3_ENDPOINT}"
aws --endpoint-url "${S3_ENDPOINT}" s3api create-bucket --bucket agentic-fs-data 2>/dev/null \
  || echo "  (bucket already exists)"

echo "creating DynamoDB table agentic-fs-catalog on ${DDB_ENDPOINT}"
aws --endpoint-url "${DDB_ENDPOINT}" dynamodb create-table \
  --table-name agentic-fs-catalog \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=GSI1PK,AttributeType=S \
    AttributeName=GSI2PK,AttributeType=S \
    AttributeName=GSI3PK,AttributeType=S \
    AttributeName=GSI3SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
    'IndexName=gsi1_by_doc,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH}],Projection={ProjectionType=ALL}' \
    'IndexName=gsi2_by_checksum,KeySchema=[{AttributeName=GSI2PK,KeyType=HASH}],Projection={ProjectionType=ALL}' \
    'IndexName=gsi3_by_extraction_status,KeySchema=[{AttributeName=GSI3PK,KeyType=HASH},{AttributeName=GSI3SK,KeyType=RANGE}],Projection={ProjectionType=ALL}' \
  2>/dev/null || echo "  (table already exists)"

echo "local init done"
