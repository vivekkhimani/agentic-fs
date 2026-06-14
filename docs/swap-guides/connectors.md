# Swap guide: connectors (bring your own source)

A connector pulls documents from a source (a folder, S3, Google Drive, …) into
agentic-fs. It's a pluggable contract — `afs_core.contracts.Connector` — so you
can crawl any source without forking. Connectors run **outside** the server and
push to the ingest REST API ([ADR 0007](../decisions/0007-connector-model.md)).

A connector's only job is **source → items + bytes**. Everything else —
change-detection, retries, calling the API, signing, pruning — is the
[`afs-connector-sdk`](../../packages/afs-connector-sdk)'s job.

## The contract

```python
class Connector(Protocol):
    name: str
    def discover(self) -> Iterable[SourceItem]      # enumerate documents
    def fetch(self, item: SourceItem) -> bytes      # get one document's bytes
```

`SourceItem` is a relative `path` (→ the doc's agentic-fs path), an opaque
`locator` (what `fetch` uses), and optional `size` / `content_type` / `version`
(a cheap change token — etag/mtime).

## Two kinds of auth (keep them separate)

- **Source-side** — how the connector reaches the source — lives **inside your
  connector**. The S3 connector uses the boto3 credential chain; a Drive
  connector does OAuth; local FS needs nothing. The contract never mentions it.
- **API-side** — how the connector authenticates to agentic-fs — is a
  `RequestSigner` the SDK supplies: `NoAuth`, `SigV4Signer` (the `AWS_IAM`
  Function URL), bearer later. You don't write this.

## Incremental sync (don't re-crawl everything)

For periodic syncs of large sources, the engine avoids redundant work in two
layers ([ADR 0008](../decisions/0008-incremental-sync.md)):

- **L1 (automatic, every connector).** The engine stamps each ingest with your
  `SourceItem.version` (etag/mtime) and, next run, **skips the fetch** for any
  file whose version is unchanged. You get this for free by populating `version`.
- **L2 (opt-in, delta sources).** If your source has a change feed, implement
  `IncrementalConnector.discover_changes(cursor) -> ChangeSet` (changed items +
  deleted paths + a new cursor). The engine persists the cursor server-side and
  next run enumerates only what changed — it never lists the unchanged tree.

```python
class IncrementalConnector(Protocol):
    name: str
    def discover(self) -> Iterable[SourceItem]          # full / first scan
    def fetch(self, item: SourceItem) -> bytes
    def discover_changes(self, cursor: str | None) -> ChangeSet   # cursor=None ⇒ everything + a start cursor
```

Local FS, S3, and Google Drive ship L1 today; Drive's delta `changes.list` (and
Graph `delta` for SharePoint) are the first L2 implementations, next up.

## Write one

1. **Implement** the `Connector` Protocol (wrap boto3, the Google API client, a
   SaaS SDK). Map each source document to a clean relative `path`.
2. **Certify** it — subclass the kit and make it green:
   ```python
   from afs_core.testing import ConnectorConformance

   class TestMyConnector(ConnectorConformance):
       @pytest.fixture
       def connector(self):
           return MyConnector(source, ...)   # pointed at a populated source
   ```
3. **Register** an entry point whose value is a `(source, **options) -> Connector`
   callable:
   ```toml
   [project.entry-points."afs.connectors"]
   gdrive = "mypkg.connector:GoogleDriveConnector"
   ```
4. **Run it** — `fs-crawler --connector gdrive --source <folder-id> --api-url … --namespace …`.

## Builtins + the CLI

`local` (a directory), `s3` (`s3://bucket/prefix/`, needs `[aws]`), and `gdrive`
(a Drive folder, needs `[gdrive]` — see [its setup guide](../connectors/gdrive.md)).
Re-runs are idempotent (skip unchanged by checksum); `--prune` mirrors deletes.

```bash
fs-crawler --connector local --source ./docs --api-url http://localhost:8080 --namespace docs
fs-crawler --connector s3 --source s3://bucket/reports/ --api-url "$URL" \
    --namespace reports --auth sigv4 --region us-east-1
```

Reference: `afs_connector_sdk`, contract in `afs_core/contracts/connector.py`,
decision in [`0007-connector-model.md`](../decisions/0007-connector-model.md).
