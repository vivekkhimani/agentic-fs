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

Coming next: `catalog_dynamodb` (DynamoDB `CatalogStore`), then the read-path
services + REST/MCP app.

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
