# agentic-fs — Terraform

Infrastructure for agentic-fs, fully modularized and deployed with one
`terraform apply` per root. Everything is `agentic-fs-*`-named and
`Project = agentic-fs`-tagged so the whole footprint is isolated, auditable, and
tearable-down by tag — even when it shares an AWS account with other workloads.

> **Status (live).** The guardrail + pipeline layer is in place and the first
> real modules are applied to the sandbox: `kms`, `storage`, and
> `catalog_dynamodb` are implemented and composed in
> [`examples/quickstart`](examples/quickstart) (5 resources live). The remaining
> modules under [`modules/`](modules/) are still scaffolds (README contracts),
> filled in milestone by milestone (`docs/agentic-fs-oss-plan.md` §15; live
> progress in [`docs/build-progress.md`](../docs/build-progress.md)). Every slice
> goes through the same pipeline: fmt → validate → tflint → trivy → read-only
> plan → gated sandbox apply → drift.

## Layout

```
terraform/
├── global/
│   ├── bootstrap/   # S3 remote-state bucket (admin-applied, once)
│   └── ci-roles/    # GitHub-OIDC plan + apply roles (admin-applied)
├── modules/         # one module per stateful layer (scaffolds today) — see modules/README.md
├── examples/
│   ├── quickstart/  # default footprint; the root CI auto-applies to sandbox
│   ├── hardened/    # defense-in-depth variant (doc stub)
│   ├── full/        # everything-on variant (doc stub)
│   └── byo-postgres/# Postgres-catalog variant (doc stub)
├── .tflint.hcl
└── .gitignore
```

## State backend

S3 remote backend with **native S3 locking** (`use_lockfile = true`, Terraform
>= 1.10) — no DynamoDB lock table. One state key per root, all in
`agentic-fs-terraform-state-<account_id>` (versioned, SSE, TLS-only).

| Root | State key |
|---|---|
| `global/bootstrap` | `global/bootstrap.tfstate` (self-hosted after migrate) |
| `global/ci-roles` | `global/ci-roles.tfstate` |
| `examples/quickstart` | `examples/quickstart.tfstate` |

## First-time setup (admin, once)

Run by a human with admin credentials, in order:

```bash
# 1. State bucket (creates the backend everything else uses)
cd terraform/global/bootstrap   # then follow its README (local apply → migrate to S3)

# 2. CI roles (optional — GitHub-OIDC plan/apply identities, if you wire CI deploy)
cd ../ci-roles
terraform init -backend-config="bucket=agentic-fs-terraform-state-${ACCOUNT_ID}"
terraform apply -var aws_account_id="${ACCOUNT_ID}" -var state_bucket_name="agentic-fs-terraform-state-${ACCOUNT_ID}"
```

Then apply `examples/quickstart` from your checkout (see its README).

## CI is validate-only — deploy is yours

`.github/workflows/terraform.yml` runs **only credential-free static checks** on
PRs — `fmt` + `validate` (`-backend=false`) + `tflint` + `trivy`. **CI never
touches an AWS account**: no plan-against-state, no apply, no stored account
secret. You deploy from your own checkout (the commands above + each example's
README), which keeps this public repo decoupled from any one account.

The `global/ci-roles` root still ships the GitHub-OIDC plan/apply identities for
anyone who *wants* to wire their own deploy pipeline — but it's opt-in, not part
of this repo's CI. Account-specific values (the account ID, the state bucket) are
inputs, never defaults; the state bucket is supplied as partial backend config at
`init` (`-backend-config="bucket=…"`).

## Tagging & teardown

Every resource inherits provider `default_tags`:

```hcl
Project   = "agentic-fs"     # the teardown selector
ManagedBy = "terraform"
Repo      = "agentic-fs"
Component = "<...>"          # or Example = "<...>"
Env       = "<sandbox|global>"
```

### Teardown runbook (tested)

Destroy in **reverse dependency order**: the example root first, then
`global/ci-roles`, last the state bucket. A few resources block a clean
`terraform destroy` and need a manual pre-step first (these are safety features,
not bugs — clearing them is a deliberate act):

```bash
ACCOUNT_ID=<your-account-id>
BUCKET="agentic-fs-terraform-state-${ACCOUNT_ID}"

# 1. Clear the destroy blockers (each would otherwise fail the destroy):
#    a. DynamoDB deletion protection (catalog default) blocks DeleteTable.
aws dynamodb update-table --table-name agentic-fs-catalog --no-deletion-protection-enabled
#    b. The data bucket is versioned with no force_destroy → purge ALL versions
#       AND delete markers (jmespath can't concat the two lists, so do each):
for k in Versions DeleteMarkers; do
  aws s3api delete-objects --bucket "agentic-fs-data-${ACCOUNT_ID}" --delete \
    "$(aws s3api list-object-versions --bucket "agentic-fs-data-${ACCOUNT_ID}" \
        --query "{Objects: ${k}[].{Key:Key,VersionId:VersionId}}" --output json)"
done
#    c. ECR repo with images blocks repo deletion → delete the images:
aws ecr batch-delete-image --repository-name agentic-fs-api \
  --image-ids "$(aws ecr list-images --repository-name agentic-fs-api --query imageIds --output json)"

# 2. Destroy the application footprint, then the CI roles:
( cd examples/quickstart && terraform init -backend-config="bucket=${BUCKET}" \
  && terraform destroy -auto-approve -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1 )
( cd global/ci-roles && terraform init -backend-config="bucket=${BUCKET}" \
  && terraform destroy -auto-approve -var aws_account_id="${ACCOUNT_ID}" -var state_bucket_name="${BUCKET}" )

# 3. The state bucket is circular (it holds every root's state), so it can't be
#    terraform-destroyed cleanly — empty its versions + delete it by hand, last:
for k in Versions DeleteMarkers; do
  aws s3api delete-objects --bucket "${BUCKET}" --delete \
    "$(aws s3api list-object-versions --bucket "${BUCKET}" \
        --query "{Objects: ${k}[].{Key:Key,VersionId:VersionId}}" --output json)"
done
aws s3api delete-bucket --bucket "${BUCKET}"

# 4. Verify — the uniform tag is the definitive "did we get everything?" check:
aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=agentic-fs
```

Notes:
- **The CMK lingers in `PendingDeletion`.** AWS never deletes a KMS key
  immediately; `terraform destroy` schedules it (7–30 day window) and it stays
  tagged until then. Expected, not a leftover.
- **`global/ci-roles` does not own the GitHub OIDC provider** (it's a data
  source), so destroying it leaves the account's OIDC provider in place — anything
  else relying on it (e.g. a separate site-deploy role) keeps working.
- **Making this one-command** would mean adding gated `force_destroy` (storage) /
  `force_delete` (ecr) toggles and a teardown-time `deletion_protection=false` —
  tracked as a `help wanted` issue; the manual pre-steps above are the safe
  default until then.

## Conventions

HashiCorp style guide: `terraform.tf` / `main.tf` / `variables.tf` /
`outputs.tf` per root and module; typed + documented variables; `for_each` over
`count` except boolean gating; `lowercase_underscore` names;
`required_version >= 1.10`, `hashicorp/aws ~> 6.0`; committed
`.terraform.lock.hcl` per root. See [`DECISIONS.md`](DECISIONS.md) for the ADRs.
