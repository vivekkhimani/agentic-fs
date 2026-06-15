# Example: full

Every capability agentic-fs ships **today**, on and production-tuned — the
"show me everything" reference. Applied from your own checkout (CI is validate-only).

```bash
cd terraform/examples/full
ACCOUNT_ID=<your-account-id>
terraform init  -backend-config="bucket=agentic-fs-terraform-state-${ACCOUNT_ID}"
terraform apply -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1 \
                -var alarm_email=ops@example.com
```

Composes: `kms` · `storage` · `catalog_dynamodb` (deletion protection + PITR) ·
`ecr_mirror` · `compute_lambda` (Function URL) · `ingestion` (async extract +
reconciler) · `observability` (alarms + email).

## Optional capability modules — not built yet

These are the headline "full" extras. They're **not faked** — each is left as a
clear slot in `main.tf` and tracked as a contribution issue (PRs very welcome):

| Capability | Module (to build) |
|---|---|
| Semantic `fs_search` | `search_bedrock_kb` (Bedrock Knowledge Base) |
| Always-on API behind an ALB | `compute_fargate` + `network` |
| Managed OAuth IdP (greenfield) | `auth_cognito` |

When a module lands it slots in behind an `enable_*` flag, the same way the
implemented modules are composed. See `docs/agentic-fs-oss-plan.md` §11 for the
full module set.
