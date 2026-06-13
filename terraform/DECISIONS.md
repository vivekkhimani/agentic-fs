# Terraform infrastructure decisions (ADRs)

Short records of the load-bearing choices in this Terraform tree. Application-
level ADRs live in `docs/decisions/` per the plan; these are infra/pipeline.

## 1. S3 remote backend with native locking — not HCP Terraform, not DynamoDB locks

**Decision.** Remote state in a single versioned/SSE/TLS-only S3 bucket, with
`use_lockfile = true` (Terraform >= 1.10) for locking. One state key per root.

**Why.** Native S3 conditional-write locking removes the DynamoDB lock table the
old pattern required — one fewer resource to create, pay for, and tear down. S3
keeps state in the same account/blast-radius as the resources it describes, with
no third-party vendor in the loop ($0, matches the project's near-$0-idle goal).
HCP Terraform was considered and rejected for v1: it adds a vendor and a second
control plane, and diverges from the plan's self-hostable, BYO-AWS design.

## 2. Plan/apply role separation over GitHub OIDC

**Decision.** Two IAM roles. `agentic-fs-terraform-plan` is read-only
(`ReadOnlyAccess` + state RW) and assumable from any job in the repo.
`agentic-fs-terraform-apply` adds scoped writes and is assumable **only** from
the gated `sandbox` GitHub Environment.

**Why.** PRs (including from forks) must be able to run a plan without ever being
able to mutate infrastructure — read-only-by-construction is a stronger
guarantee than "we promise the apply step is gated". No long-lived AWS keys:
OIDC federation only.

## 2a. Apply-role writes: permissions boundary, not action enumeration

**Decision.** The apply role gets broad writes (`ReadOnlyAccess` +
`PowerUserAccess` + IAM writes scoped to `agentic-fs-*`) capped by a permissions
boundary (`agentic-fs-ci-boundary`). It is **not** a hand-enumerated allow-list
of per-resource actions.

**Why.** Per-action enumeration is a treadmill — every new resource type means
editing this root, and `plan` (read-only) can't warn you about a missing write;
only `apply` fails. A permissions boundary inverts the model: grant breadth,
then hard-cap the blast radius. Effective authority is `identity ∩ boundary`, so
the boundary's denies (region lock, state-bucket protection, no self-IAM
escalation, created-roles-must-inherit-the-boundary, no org/billing) hold no
matter how broad the identity policy is. This is safe specifically because the
role is OIDC-only, short-lived, and assumable solely from the gated `sandbox`
environment — and because this role only protects the *maintainer's* sandbox;
OSS adopters apply with their own credentials. Net effect: touch ci-roles ~once
per new AWS *service*, not once per resource. Considered and rejected:
`AdministratorAccess` (no blast-radius cap) and per-action enumeration (the
treadmill). A consequence: any role a module creates must inherit the boundary
(`permissions_boundary = <permissions_boundary_arn>`), or its creation is denied
— enforced, not just advised.

## 3. Single `sandbox` environment — not staging/production

**Decision.** One GitHub Environment (`sandbox`) and one CI-managed root
(`examples/quickstart`).

**Why.** agentic-fs is an OSS, BYO-AWS product, not a multi-stage hosted
service. The pipeline's job is to prove the quickstart applies cleanly in a
maintainer sandbox; adopters run the same Terraform in their own accounts. A
two-environment promotion flow would be ceremony with no consumer. (Revisit if a
hosted demo environment is ever added.)

## 4. CI manages examples; global roots are admin-applied

**Decision.** `global/bootstrap` and `global/ci-roles` are applied by a human
with admin credentials, never by CI. The apply role cannot modify the state
bucket or its own IAM roles.

**Why.** A CI role that can rewrite its own trust policy or delete the state
bucket defeats the point of scoping it. Bootstrapping identity and state is a
privileged, rare, deliberate act — it stays out of the automated path.

## 5. Tag everything with `Project = agentic-fs` for teardown

**Decision.** Provider `default_tags` stamp `Project`, `ManagedBy`, `Repo`,
`Component`/`Example`, and `Env` on every resource. `Project = agentic-fs` is the
canonical teardown selector.

**Why.** The footprint shares the existing Seamind account during the trial, so
clean separation and confident teardown were requirements from the start. A
uniform tag makes "list everything this project created" a single
`get-resources --tag-filters Key=Project,Values=agentic-fs` query — the
definitive check that a `terraform destroy` sweep left nothing behind.

## 6. Skeleton-first guardrails

**Decision.** Ship the full pipeline (state, roles, workflows, lint/scan,
drift, tagging) against an empty `quickstart` root before any application module
exists.

**Why.** Proving fmt → validate → tflint → trivy → plan → gated apply → drift on
a no-op root means the first real resource lands into a pipeline already known to
be green and correctly permissioned — guardrails before payload, exactly the
order requested.
