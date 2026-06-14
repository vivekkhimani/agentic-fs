# afs-connector-sdk

Crawl a source and ingest its documents into [agentic-fs](https://github.com/vivekkhimani/agentic-fs).
Ships the `fs-crawler` CLI plus **Local FS** and **S3** connectors.

```bash
pip install afs-connector-sdk          # Local FS connector + unauthenticated/bearer APIs
pip install "afs-connector-sdk[aws]"   # adds the S3 connector + SigV4 signing for AWS_IAM Function URLs
```

## CLI

```bash
# Crawl a local folder into a dev server
fs-crawler --connector local --source ./docs \
  --api-url http://localhost:8080 --namespace docs

# Crawl an S3 prefix into the deployed (AWS_IAM) Function URL
fs-crawler --connector s3 --source s3://my-bucket/reports/ \
  --api-url "$FUNCTION_URL" --namespace reports --auth sigv4 --region us-east-1

# Mirror exactly (also delete docs no longer at the source)
fs-crawler --connector local --source ./docs --api-url "$URL" --namespace docs --prune
```

Re-runs are cheap and idempotent: a document is skipped unless its content
checksum differs from what agentic-fs already has, so nothing is re-extracted
needlessly.

## Library

```python
from afs_connector_sdk import IngestClient, SyncEngine, SigV4Signer, build_connector

connector = build_connector("local", "./docs")
async with IngestClient(api_url, signer=SigV4Signer(region="us-east-1")) as client:
    report = await SyncEngine(client).sync(connector, namespace="docs")
```

## Writing a connector

Implement `afs_core.contracts.Connector` (`discover()` → `SourceItem`s, `fetch(item)` →
bytes), certify it against `afs_core.testing.ConnectorConformance`, and register an
`afs.connectors` entry point. Source-side auth lives in your connector; the SDK
handles everything else. See [the connector swap guide](../../docs/swap-guides/connectors.md).
