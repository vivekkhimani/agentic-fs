# Terraform CI roles

Defines the two GitHub-OIDC roles the agentic-fs Terraform pipeline assumes,
following least-privilege + plan/apply separation:

| Role | Trust (OIDC subject) | Permissions | Used by |
|---|---|---|---|
| `agentic-fs-terraform-plan` | `repo:vivekkhimani/agentic-fs:*` | `ReadOnlyAccess` + state-bucket RW/lock | PR `plan`, scheduled drift |
| `agentic-fs-terraform-apply` | `…:environment:sandbox` only | `ReadOnlyAccess` + scoped infra writes + state-bucket RW/lock | apply job (env-gated) |

The plan role **cannot mutate infrastructure** — PRs (including from forks) run
plans that are read-only by construction. The apply role holds the write
permissions and is only assumable from a job that declares
`environment: sandbox`, which carries the approval gate configured in the repo's
GitHub Environment settings.

Reads come from the broad AWS-managed `ReadOnlyAccess` (so plans never fail on a
missing read permission); the **write** surface is kept tight and is **widened
one milestone at a time** in the `apply_writes` block in `main.tf` (commented
out today, because the skeleton manages no application resources yet).

## Prerequisites

- The [`../bootstrap`](../bootstrap) state bucket must already exist (this root
  stores its state there).
- The account's GitHub OIDC provider (`token.actions.githubusercontent.com`)
  must exist. It is shared and already present in account `002988089284`; this
  root references it as a data source.

## Applying (admin, one-time and on changes)

This root manages IAM, so a human with admin credentials applies it — CI does
not have permission to modify its own roles.

```bash
cd terraform/global/ci-roles
terraform init
terraform plan      # review: 2 roles + policies
terraform apply
```

Then confirm the workflows reference these roles by name (they do, via
`secrets.AWS_ACCOUNT_ID`):

- `plan_role_arn`  → `.github/workflows/terraform.yml` (plan job) + `terraform-drift.yml`
- `apply_role_arn` → `.github/workflows/terraform.yml` (apply + dispatch jobs)

## Extending write permissions per milestone

When a milestone brings a new resource type under Terraform, uncomment/extend the
`apply_writes` policy document in `main.tf` with that type's mutating actions
(reads are already covered by `ReadOnlyAccess`), scope it by ARN/prefix, and
re-apply. Never widen to `s3:*` / `*`.
