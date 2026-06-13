# Terraform CI roles

Defines the two GitHub-OIDC roles the agentic-fs Terraform pipeline assumes,
following least-privilege + plan/apply separation:

| Role | Trust (OIDC subject) | Permissions | Used by |
|---|---|---|---|
| `agentic-fs-terraform-plan` | `repo:vivekkhimani/agentic-fs:*` | `ReadOnlyAccess` + state-bucket RW/lock | PR `plan`, scheduled drift |
| `agentic-fs-terraform-apply` | `…:environment:sandbox` only | `ReadOnlyAccess` + `PowerUserAccess` + scoped IAM writes, **capped by `agentic-fs-ci-boundary`** | apply job (env-gated) |

The plan role **cannot mutate infrastructure** — PRs (including from forks) run
plans that are read-only by construction. The apply role holds the write
permissions and is only assumable from a job that declares
`environment: sandbox`, which carries the approval gate configured in the repo's
GitHub Environment settings.

### Apply-role permission model: bounded breadth, not action enumeration

Rather than enumerate every resource's write actions (a per-milestone treadmill
that `plan` can't even warn you about — only `apply` fails on a missing perm),
the apply role is granted **broad writes** and capped by a **permissions
boundary**:

- identity = `ReadOnlyAccess` (all reads incl. IAM) + `PowerUserAccess` (all
  non-IAM writes) + `agentic-fs-iam-writes` (IAM writes scoped to `agentic-fs-*`).
- boundary = **`agentic-fs-ci-boundary`** — the hard cap. Effective authority is
  `identity ∩ boundary`, so the breadth above can never escape it. The boundary
  denies:
  - regional actions outside `us-east-1` (global services excepted);
  - deleting/reconfiguring the **state bucket** (object RW stays allowed);
  - any IAM edit to the **CI roles or the boundary itself** (no self-escalation);
  - creating a role **without inheriting this same boundary** (escalation
    prevention) and creating IAM users/access keys/login profiles;
  - `organizations:*` / `account:*` / billing.

This is safe because the role is OIDC-only, short-lived, assumable solely from
the gated `sandbox` environment, and bounded — so a compromised pipeline still
can't leave the project's blast radius. It also means you touch this root **at
most once per new AWS service**, not once per resource.

> **Module authors:** any IAM role a module creates (e.g. a Lambda exec role)
> **must** set `permissions_boundary` to the `permissions_boundary_arn` output of
> this root — otherwise the apply role's boundary will *deny* its creation. Thread
> that ARN in as a variable. (M0's `kms`/`storage` create no roles, so this first
> bites at `compute_lambda`.)

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

## When you actually need to touch this root

With the boundary model, milestones that add resources for services the apply
role can already reach (S3, DynamoDB, Lambda, KMS, SQS, EventBridge, Cognito,
Bedrock, …) need **no change here** — `PowerUserAccess` already covers them and
the boundary keeps them in-scope. You only re-apply this root to:

- **widen the boundary** if a milestone legitimately needs a region beyond
  `us-east-1`, or a service the boundary currently blocks; or
- **add IAM writes** if a new module manages an IAM resource type not already in
  `agentic-fs-iam-writes`.

Keep changes scoped (`agentic-fs-*`, the home region) and never weaken the
self-protection / escalation-prevention denies.
