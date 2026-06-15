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

To tear the project down cleanly:

1. `terraform destroy` each root in **reverse dependency order**: examples first,
   then `global/ci-roles`, last `global/bootstrap` (its bucket has
   `prevent_destroy = true` — remove that guard deliberately, or empty + delete
   the bucket by hand).
2. Verify nothing is left behind by listing everything tagged `Project=agentic-fs`
   (AWS Resource Groups / Tag Editor, or:
   `aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=agentic-fs`).

Because the tag is uniform across the whole footprint, that one query is the
definitive "did we get everything?" check — the reason teardown was a design
goal from day one.

## Conventions

HashiCorp style guide: `terraform.tf` / `main.tf` / `variables.tf` /
`outputs.tf` per root and module; typed + documented variables; `for_each` over
`count` except boolean gating; `lowercase_underscore` names;
`required_version >= 1.10`, `hashicorp/aws ~> 6.0`; committed
`.terraform.lock.hcl` per root. See [`DECISIONS.md`](DECISIONS.md) for the ADRs.
