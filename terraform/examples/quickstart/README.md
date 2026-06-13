# Example: quickstart

The default, near-$0-idle agentic-fs footprint and the root the CI pipeline
auto-applies into the `sandbox` GitHub Environment on merge to `master`.

**Variable budget:** `aws_region` is the only required input; everything else is
defaulted (plan §11.3).

```bash
cd terraform/examples/quickstart
terraform init
terraform plan -var aws_region=us-east-1
terraform apply -var aws_region=us-east-1
```

## Composed so far

| Module | Milestone | What it creates |
|---|---|---|
| `kms` | M0 | the project CMK (`alias/<name_prefix>-data`) + key policy |
| `storage` | M0 | the canonical data bucket (`<name_prefix>-data-<account_id>`): versioned, SSE-KMS, TLS-only, lifecycle'd, EventBridge-enabled |
| `catalog_dynamodb` | M1 | the derived catalog table (`<name_prefix>-catalog`): PAY_PER_REQUEST, PITR, deletion protection, SSE-KMS, TTL, 3 GSIs |

Outputs: `data_bucket_name`, `data_bucket_arn`, `kms_key_arn`,
`catalog_table_name`, `catalog_table_arn`. Later modules (ingestion, compute,
auth, observability) are wired in here milestone-by-milestone
(`docs/agentic-fs-oss-plan.md` §15).

## Prerequisites

1. [`../../global/bootstrap`](../../global/bootstrap) applied (the state bucket
   this root's backend points at).
2. [`../../global/ci-roles`](../../global/ci-roles) applied (so CI can plan/apply).
3. The `AWS_ACCOUNT_ID` repo secret set and the `sandbox` GitHub Environment
   created (see [`../../README.md`](../../README.md)).

## The other examples

`hardened`, `full`, and `byo-postgres` are documented variants of this same
composition (different flags / module sets). They are doc stubs until the
modules they compose exist.
