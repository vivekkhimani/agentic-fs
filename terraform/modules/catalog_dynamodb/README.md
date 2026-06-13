# `catalog_dynamodb` — DynamoDB catalog (default)

The default `CatalogStore` backend (plan §5.1): a single DynamoDB table that is
the **derived index** of S3. It answers `list`/`glob`/`stat` and holds control
records (tenants/namespaces/principals), connector checkpoints, scratch usage,
and idempotency locks. It is rebuildable from the data bucket — the M2 reconciler
diffs the two — so it is never the source of truth.

## Resources

- `aws_dynamodb_table.catalog` — `<name_prefix>-catalog`, `PAY_PER_REQUEST`.
  - keys: `PK` (hash) + `SK` (range), generic — value schemes live in the app.
  - PITR enabled, deletion protection enabled, SSE-KMS with the project CMK.
  - TTL on `expires_at` (expires idempotency locks + ephemeral items).
  - GSIs:
    | GSI | Key(s) | Purpose |
    |---|---|---|
    | `gsi1_by_doc` | `GSI1PK` | resolve a `doc_id` to its item(s) |
    | `gsi2_by_checksum` | `GSI2PK` | dedupe / idempotency by content hash |
    | `gsi3_by_extraction_status` | `GSI3PK` + `GSI3SK` | **sparse** — ops queries ("all failed", "stuck > 1h") |

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | string | — | Table name prefix. |
| `kms_key_arn` | string | — | Project CMK for SSE-KMS. |
| `deletion_protection_enabled` | bool | `true` | Block accidental deletion. |
| `point_in_time_recovery_enabled` | bool | `true` | Continuous backups. |

## Outputs

| Name | Description |
|---|---|
| `table_name` | Catalog table name. |
| `table_arn` | Catalog table ARN. |
| `table_stream_arn` | Stream ARN (null unless streams enabled later). |

## Swappable

This is one of two reference implementations of the `CatalogStore` contract; the
other is `catalog_postgres` (BYO-RDS). The schema here intentionally maps to the
same logical contract — see `docs/swap-guides/catalog.md` (plan §5.1).
