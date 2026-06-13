# afs-core

The **contracts** package for agentic-fs: `typing.Protocol` interfaces, pydantic
DTOs, the single key scheme, the closed error vocabulary, versioned event
contracts, and the conformance test kits. Depends on **pydantic only** — it
imports without the server, so connectors and adopters can build against it
without pulling in `afs-server`.

## Status

Foundations slice (M0, in progress):

- `afs_core.keys` — the **single** definition of the S3 key scheme: build, parse,
  validate, and `is_indexable()`. Nothing else concatenates a key.
- `afs_core.errors` — the closed `ErrorCode` vocabulary + the `AfsError`
  hierarchy (RFC 9457 `problem+json` shape).
- `afs_core.models` — core DTOs (`Page[T]`, `CatalogEntry`, `ExtractionState`, …)
  and control records (`TenantRecord`, `NamespaceRecord`, `PrincipalRecord`).

Coming next: `afs_core.contracts` (the async Protocols), `afs_core.testing`
(conformance kits + in-memory fakes), `afs_core.events`.

## Develop

```bash
uv sync
uv run pytest packages/afs-core
```
