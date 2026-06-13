# `catalog_dynamodb` — DynamoDB catalog (default)

**Status: scaffold (not yet implemented).** Default footprint.

Single-table catalog with 3 GSIs, TTL, PITR, deletion protection, and SSE-KMS — the default CatalogStore backend.

The full input/output contract for this module lives in the index table in
[`../README.md`](../README.md). It will be implemented per the milestone plan
(`docs/agentic-fs-oss-plan.md` §11, §15); when it lands, add its mutating IAM
actions to the apply role's `apply_writes` scope in
[`../../global/ci-roles`](../../global/ci-roles) in the same change.

Conventions: HashiCorp style-guide layout (`terraform.tf`/`main.tf`/`variables.tf`/`outputs.tf`),
typed + documented variables, `<name_prefix>-<component>` naming, no
backend/provider block (composed from the example roots).
