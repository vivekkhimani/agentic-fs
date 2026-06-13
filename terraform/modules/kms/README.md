# `kms` — project CMK

The shared customer-managed key used for SSE-KMS across agentic-fs's stateful
layers (data bucket today; catalog table and derived stores as they land).

## Resources

- `aws_kms_key.this` — CMK with rotation enabled, configurable deletion window.
- `aws_kms_alias.this` — `alias/<name_prefix>-data`.
- Key policy granting the **account root** full control; every other grant is
  delegated through IAM policies on the consuming principals (the AWS-recommended
  default — IAM stays the single place authority is granted).

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | string | — | Prefix for the alias (`alias/<name_prefix>-data`). |
| `deletion_window_in_days` | number | `30` | CMK deletion waiting period (7–30). |

## Outputs

| Name | Description |
|---|---|
| `key_arn` | CMK ARN — pass to `storage` (and future `catalog_dynamodb`). |
| `key_id` | CMK key id. |
| `alias_arn` | Alias ARN. |

## Deferred

`per_tenant_kms` (plan §4.3) — premium per-tenant cryptographic isolation. v1
ships the key-policy template + the app-side `tenant -> key_id` seam; the
automated key-fleet lifecycle is control-plane-shaped and is added here as a
`per_tenant_kms` flag + `for_each` fleet when that work lands.
