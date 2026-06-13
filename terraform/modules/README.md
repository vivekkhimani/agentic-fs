# agentic-fs Terraform modules

One module per stateful layer, following HashiCorp style-guide conventions
(`terraform.tf` / `main.tf` / `variables.tf` / `outputs.tf` per module, typed +
documented variables, `for_each` over `count` except boolean gating,
`lowercase_underscore` names). Every module is composed from the example roots
under [`../examples`](../examples); modules never configure a backend or a
provider of their own.

These are **scaffolds** — each directory currently holds only this contract in a
README. Modules are implemented milestone-by-milestone (see the plan, §15) and
the apply role's write scope is widened in lockstep (see
[`../global/ci-roles`](../global/ci-roles)).

## Default footprint (quickstart)

| Module | Status | Key resources | Notable inputs | Notable outputs |
|---|---|---|---|---|
| `kms` | scaffold | CMK + alias + key policy (incl. per-tenant key template) | `name_prefix`, `per_tenant_kms` | `key_arn`, `key_id` |
| `storage` | scaffold | data bucket, policy, lifecycle, EventBridge enable, optional access-logs bucket | `name_prefix`, `kms_key_arn`, `scratch_ttl_days`, `enable_access_logs`, `quarantine_exempt_role_arns` | `bucket_name`, `bucket_arn` |
| `catalog_dynamodb` | scaffold | table + 3 GSIs + TTL + PITR (default catalog) | `name_prefix`, `kms_key_arn` | `table_name`, `table_arn` |
| `ingestion` | scaffold | EventBridge rules, SQS + DLQ, extractor Lambda + ESM, reconciler, scheduler | `bucket_*`, `table_*`, `extractor_image_uri`, `max_concurrency`, `reconcile_schedule`, `enable_scan_gate` | `extract_queue_arn`, `dlq_arn` |
| `compute_lambda` | scaffold | api Lambda, Function URL (stream), exec role, ABAC tenant-scoped role (default serving compute) | `api_image_uri`, `bucket_*`, `table_*`, `oidc_issuer`, `oidc_audience`, `auth_mode`, `enable_session_policy_scoping`, `enable_scratch`, `search_kb_id`, `provisioned_concurrency` | `function_url`, `api_role_arn` |
| `observability` | scaffold | log groups, SNS topic, 5 alarms, optional dashboard/budget/CloudTrail | function/queue names, `alarm_email`, `log_retention_days` | `alerts_topic_arn` |
| `ecr_mirror` | scaffold | private ECR repos + pinned-version image copy (Lambda needs same-account ECR) | `name_prefix`, `release_version` | `api_repo_url`, `extractor_repo_url` |

## Optional modules (flag-gated)

| Module | Status | Enabled by | Purpose |
|---|---|---|---|
| `catalog_postgres` | scaffold | `AFS_CATALOG=postgres` | BYO-RDS alternative catalog: DSN secret + IAM grant + env wiring (creates **no** database) |
| `compute_fargate` | scaffold | `enable_fargate` | Same image behind an ALB for always-on / no-cold-start / OCR-at-scale |
| `network` | scaffold | `enable_fargate` | Minimal VPC (public-subnet + locked SG by default; private+NAT documented variant) |
| `search_bedrock_kb` | scaffold | `enable_search` | Vector bucket + index, Bedrock Knowledge Base, data source, role, sync schedule |
| `auth_cognito` | scaffold | `enable_cognito` (default on) | User pool, resource server + scopes, clients → issuer/audience outputs |
| `security_guardduty` | scaffold | `enable_guardduty_scan` | Malware protection plan, scan-result rule, quarantine policy |

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
- **Validation:** `terraform fmt` + `validate` + `tflint` in CI; per-module
  `*.tftest.hcl` with `command = plan` and mocked providers assert policy JSON,
  flag-conditional resource counts, and naming; `terraform-docs` keeps each
  module README in sync.
