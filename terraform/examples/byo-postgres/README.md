# Example: byo-postgres (doc stub)

**Status: documented, not yet buildable** — composes modules that are still
scaffolds. This file reserves the shape; the `.tf` lands with the modules.

The `quickstart` footprint with the catalog swapped from DynamoDB to a
bring-your-own Postgres database:

- `AFS_CATALOG = postgres`
- composes `catalog_postgres` (DSN secret + IAM grant + env wiring) instead of
  `catalog_dynamodb` — it creates **no** database; you point it at an existing
  RDS/Aurora instance via the connection secret.

This is the worked example for the catalog swap guide
(`docs/swap-guides/catalog.md`). Until then, use [`../quickstart`](../quickstart).
See `docs/agentic-fs-oss-plan.md` §5.1 and §11.
