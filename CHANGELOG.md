# Changelog

All notable changes to agentic-fs are documented here. The project follows
[semantic versioning](https://semver.org); the three packages
(`afs-core`, `afs-server`, `afs-connector-sdk`) version together.

## 1.0.1

Maintenance release: dependency hygiene and a container base-image bump. No
public API changes.

- **Dependencies**: raised floors for `uvicorn[standard]` (>=0.49), `fastapi`
  (>=0.137), and `pdfplumber` (>=0.11.10), and capped `pypdfium2` to `>=4,<6`
  (it ships breaking API cleanups on majors; the `pdf` rung is verified against
  5.x). Lockfile regenerated.
- **Container images**: API and worker images move from Python 3.12 to 3.13
  across every build stage (builder and runtime kept in lockstep so manylinux
  wheels stay ABI-compatible). The worker's site-packages COPY now globs the
  Python minor so future bumps can't strand the path.
- **CI**: prebuilt API + worker images publish to GHCR on each release tag.

## 1.0.0

First public release.

### Highlights

- **Contracts + conformance kits** (`afs-core`): `ObjectStore`, `CatalogStore`,
  `Normalizer`, `Connector`, and `Tool` Protocols, the key scheme, the closed
  error vocabulary, and conformance kits that certify every backend.
- **Service** (`afs-server`): the `FsService` read path, the `IngestService` +
  extraction pipeline (10 rungs, Haystack engine, presets, content-type routing),
  a FastAPI app, and an **MCP mount** with a pluggable tool registry + uniform
  middleware (visibility, scope enforcement, per-call output budget, audit).
  Tools: `whoami`, `fs_list`, `fs_stat`, `fs_read` (ranged or by section),
  `fs_glob`, `fs_grep` (two-stage, bounded), `fs_tree`, `fs_find`, `fs_outline`,
  `fs_tables`, `fs_diff`, and `scratch_*`.
- **Stores**: `S3ObjectStore` (any S3-compatible endpoint), `FsspecObjectStore`
  (GCS/Azure/HDFS/local), `DynamoDBCatalogStore`. All certified by one kit.
- **Auth**: an IdP-agnostic OAuth 2.1 resource server (bring your own IdP) plus an
  `afs auth doctor` CLI.
- **Connectors** (`afs-connector-sdk`): the `fs-crawler` CLI + sync engine with
  incremental sync, Local FS / S3 / Google Drive connectors, and a LlamaHub
  reader adapter (300+ community readers).
- **Infrastructure**: per-layer Terraform modules and a `quickstart` example;
  async ingestion (EventBridge → SQS → worker), a scheduled reconciler, and
  high-signal CloudWatch alarms.

License: Apache-2.0.
