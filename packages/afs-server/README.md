# afs-server

The agentic-fs service: the concrete backends (stores, search, extraction), the
services, and the REST + MCP surface. Implements the `afs-core` contracts.

## Status

Store layer (in progress):

- `afs_server.settings` — `AFS_*` env config; every swappable layer is selected
  by a backend *name* and every AWS-shaped backend takes an `endpoint_url`
  override.
- `afs_server.stores` — the **store registry**: `get_object_store(settings)`
  selects a builtin or an installed plugin (`afs.object_stores` entry-point group).
- `afs_server.stores.objects_s3.S3ObjectStore` — the S3 `ObjectStore`. Because it
  speaks plain S3, it *is* your store for any S3-compatible endpoint (MinIO,
  Cloudflare R2, Wasabi, Backblaze B2) via `AFS_S3_ENDPOINT_URL` — no code change.
- `afs_server.stores.catalog_dynamodb.DynamoDBCatalogStore` — the DynamoDB
  `CatalogStore` over the single-table schema (`AFS_DYNAMODB_ENDPOINT_URL` points
  at DynamoDB Local for dev).

Both stores are certified by the afs-core conformance kits via `moto`.

- `afs_server.services.FsService` — the read path (`list` / `stat` / ranged
  `read`) over the stores, with scope + namespace enforcement and 404-not-403
  misses.
- `afs_server.app` — the FastAPI app: `/v1/healthz`, `/readyz`, `/me`, and
  `fs/{ns}/{entries,stat,doc}`; dev auth (static principal, never prod); every
  `AfsError` rendered as RFC 9457 `problem+json`.
- `afs_server.mcp` — the MCP surface mounted at `/mcp` (FastMCP): `whoami`,
  `fs_list`, `fs_stat`, `fs_read` over the *same* `FsService` (in-process, no HTTP
  self-calls). The full middleware chain + remaining tools land with their slices.

The image (`../../Dockerfile`) runs this app on Lambda / Fargate / locally;
`make dev` from the repo root runs it against MinIO + DynamoDB Local. Coming
next: the MCP mount (shares `FsService` in-process).

## Swapping a backend (plug-and-play)

See [`docs/swap-guides/`](../../docs/swap-guides/). In short: S3-compatible
storage needs only an env var; anything else implements the `ObjectStore`
Protocol, registers an entry point, and certifies against
`afs_core.testing.ObjectStoreConformance`.

## Develop

```bash
uv sync
uv run pytest packages/afs-server     # conformance kits run against moto
```
