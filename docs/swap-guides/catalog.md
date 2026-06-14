# Swap guide: catalog store

The catalog is the **derived index** of S3 — it answers `list`/`glob`/`stat` and
holds control records, checkpoints, and scratch usage. agentic-fs talks to it
through one contract, `afs_core.contracts.CatalogStore`, so it's swappable as a
single stateful dependency.

## Default: DynamoDB

`DynamoDBCatalogStore` over the single table the `catalog_dynamodb` Terraform
module provisions (`PK`/`SK` + three GSIs + TTL). Configure:

```bash
export AFS_CATALOG_BACKEND=dynamodb
export AFS_CATALOG_TABLE=agentic-fs-catalog
# local dev against DynamoDB Local:
export AFS_DYNAMODB_ENDPOINT_URL=http://localhost:8000
```

The whole catalog is **rebuildable from S3**, so its loss is recoverable — it is
never the source of truth.

## Writing another catalog backend (e.g. Postgres)

Same three steps as any layer:

1. **Implement** `CatalogStore` (entries + control records + checkpoints + scratch
   quota — one contract). Keep `adjust_scratch_usage` atomic (a conditional
   `UPDATE … RETURNING` in SQL; a conditional update in DynamoDB).
2. **Certify** it — subclass the kit and make it green:
   ```python
   from afs_core.testing import CatalogStoreConformance

   class TestMyCatalog(CatalogStoreConformance):
       @pytest.fixture
       def store(self):
           return MyCatalog(...)
   ```
   The kit checks the load-bearing guarantees: tenant isolation, stable prefix
   pagination, tombstone→hard-delete, **tombstone→revive** (a re-`put` clears
   `deleted_at`), atomic extraction state + sparse status index, `tree_version`
   bump-on-write, find-by-checksum, and **atomic** scratch quota.

> **Reconciliation is free.** The scheduled catalog↔S3 reconciler
> ([ADR 0011](../decisions/0011-reconciliation.md)) is written against this
> contract — `list_entries(include_deleted=True)`, soft `delete_entry`, the
> tombstone→revive round-trip, `list_tenants`/`list_namespaces`. Pass the
> conformance kit and your backend reconciles like the default; you don't write
> your own. (Non-AWS deployments just call `afs_server.reconcile.reconcile()` from
> their own scheduler.)
3. **Register** an entry point and select it:
   ```toml
   [project.entry-points."afs.catalog_stores"]
   postgres = "afs_server.stores.catalog_postgres:build"
   ```
   ```bash
   export AFS_CATALOG_BACKEND=postgres
   ```

The `catalog_postgres` Terraform module is **BYO-database** — it wires the DSN
secret + IAM grant, it does **not** create an RDS instance (plan §5.1).

## Contract reference

`afs_core/contracts/catalog.py`. Certified by
`afs_core.testing.CatalogStoreConformance`. Reference impls:
`afs_server.stores.catalog_dynamodb.DynamoDBCatalogStore` (production) and
`afs_core.testing.InMemoryCatalogStore` (tests).
