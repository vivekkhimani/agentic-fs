# agentic-fs Terraform modules

One module per stateful layer, following HashiCorp style-guide conventions
(`terraform.tf` / `main.tf` / `variables.tf` / `outputs.tf` per module, typed +
documented variables, `for_each` over `count` except boolean gating,
`lowercase_underscore` names). Every module is composed from the example roots
under [`../examples`](../examples); modules never configure a backend or a
provider of their own.

`kms`, `storage`, and `catalog_dynamodb` are **implemented** (✅) and live in the
sandbox; the rest are **scaffolds** (📝) — a contract in a README. Modules are
implemented milestone-by-milestone (see the plan, §15) and
the apply role's write scope is widened in lockstep (see
[`../global/ci-roles`](../global/ci-roles)).

## Default footprint (quickstart)

| Module | Status | Key resources | Notable inputs | Notable outputs |
|---|---|---|---|---|
| `kms` | ✅ done | CMK + alias + key policy (per-tenant template deferred) | `name_prefix`, `deletion_window_in_days` | `key_arn`, `key_id`, `alias_arn` |
| `storage` | ✅ done | data bucket, policy, lifecycle, EventBridge enable (access-logs bucket deferred) | `name_prefix`, `account_id`, `kms_key_arn`, `scratch_ttl_days`, `tenants_noncurrent_days`, `enable_intelligent_tiering`, `quarantine_exempt_role_arns` | `bucket_name`, `bucket_arn` |
| `catalog_dynamodb` | ✅ done | table + 3 GSIs + TTL + PITR + deletion protection (default catalog) | `name_prefix`, `kms_key_arn`, `deletion_protection_enabled`, `point_in_time_recovery_enabled` | `table_name`, `table_arn`, `table_stream_arn` |
| `ingestion` | 📝 scaffold | EventBridge rules, SQS + DLQ, extractor Lambda + ESM, reconciler, scheduler | `bucket_*`, `table_*`, `extractor_image_uri`, `max_concurrency`, `reconcile_schedule`, `enable_scan_gate` | `extract_queue_arn`, `dlq_arn` |
| `compute_lambda` | ✅ done | api Lambda (image) + streaming Function URL + boundary-bound exec role (least-priv read) | `image_uri`, `bucket_*`, `catalog_table_*`, `kms_key_arn`, `permissions_boundary_arn`, `function_url_auth_type`, `auth_mode`, `memory_mb`, `timeout_seconds` | `function_url`, `function_arn`, `exec_role_arn` |
| `observability` | 📝 scaffold | log groups, SNS topic, 5 alarms, optional dashboard/budget/CloudTrail | function/queue names, `alarm_email`, `log_retention_days` | `alerts_topic_arn` |
| `ecr_mirror` | ✅ done | private ECR repo for the API image (image-mirror half deferred) | `name_prefix`, `untagged_expiry_days` | `repository_url`, `repository_arn` |

## Optional modules (flag-gated)

| Module | Status | Enabled by | Purpose |
|---|---|---|---|
| `catalog_postgres` | 📝 scaffold | `AFS_CATALOG=postgres` | BYO-RDS alternative catalog: DSN secret + IAM grant + env wiring (creates **no** database) |
| `compute_fargate` | 📝 scaffold | `enable_fargate` | Same image behind an ALB for always-on / no-cold-start / OCR-at-scale |
| `network` | 📝 scaffold | `enable_fargate` | Minimal VPC (public-subnet + locked SG by default; private+NAT documented variant) |
| `search_bedrock_kb` | 📝 scaffold | `enable_search` | Vector bucket + index, Bedrock Knowledge Base, data source, role, sync schedule |
| `auth_cognito` | 📝 scaffold | `enable_cognito` (default on) | User pool, resource server + scopes, clients → issuer/audience outputs |
| `security_guardduty` | 📝 scaffold | `enable_guardduty_scan` | Malware protection plan, scan-result rule, quarantine policy |

## Flags

Some capabilities are a **flag, not a module** — they thread through existing
modules rather than standing up their own resources:

- `enable_scratch` → storage lifecycle + compute env + catalog quota items
- `per_tenant_kms` → key-fleet template in `kms` + app-side `tenant → key_id` seam
- `enable_access_logs`, `enable_session_policy_scoping`,
  `enable_cloudtrail_data_events` → toggle resources inside `storage` /
  `compute_lambda` / `observability`

## Conventions every module follows

- **Naming:** every resource is `${var.name_prefix}-<component>`; globally-unique
  names are suffixed `-${account_id}`.
- **Tagging:** provider `default_tags` at the root carry
  `Project = agentic-fs`, `ManagedBy = terraform`, `Repo`, `Component`, `Env` —
  so the entire footprint is discoverable and tearable-down by tag
  (see [`../README.md`](../README.md#teardown)).
- **IAM roles must inherit the CI boundary:** any module that creates an
  `aws_iam_role` (e.g. `compute_lambda`, `compute_fargate`, `ingestion`) must
  expose a `permissions_boundary_arn` variable and set it on every role it
  creates. The CI apply role's own permissions boundary *denies* creating a role
  that doesn't carry the same boundary (escalation prevention) — so an unbounded
  role would fail to apply in CI. Wire the `permissions_boundary_arn` output of
  [`../global/ci-roles`](../global/ci-roles) through the example roots into these
  modules. See [`../DECISIONS.md`](../DECISIONS.md) §2a.
- **Validation:** `terraform fmt` + `validate` + `tflint` in CI; per-module
  `*.tftest.hcl` with `command = plan` and mocked providers assert policy JSON,
  flag-conditional resource counts, and naming; `terraform-docs` keeps each
  module README in sync.
