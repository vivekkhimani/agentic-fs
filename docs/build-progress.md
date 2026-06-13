# agentic-fs — build progress & roadmap

> A living map from **what we've built** to **the vision** (`agentic-fs-oss-plan.md`).
> Updated as each slice lands. Last updated: 2026-06-13.

## The vision in one line

Give AI agents **filesystem-style access to an org's documents** — `list` /
`glob` / `grep` / ranged `read` / semantic `search` — over documents in **their
own S3**, exposed through **MCP + REST**, multi-tenant, deployable with **one
`terraform apply`**, **~$2/mo idle**, with **every stateful layer swappable**.

We are building it **infrastructure-first**: the deployment guardrails and the
canonical storage substrate before the application code, so every later slice
lands into a pipeline and a data model already proven safe.

## Where we are right now (live in AWS `002988089284`)

| Resource | Role in the vision |
|---|---|
| `agentic-fs-terraform-state-…` (S3) | Remote state — the "one `terraform apply`" promise rests on this |
| `agentic-fs-terraform-{plan,apply}` (IAM) + `agentic-fs-ci-boundary` | Safe, least-privilege CI delivery — guardrails before payload |
| `alias/agentic-fs-data` → CMK | **SSE-KMS everywhere** — the encryption floor of the security model |
| `agentic-fs-data-…` (S3) | **S3 is canonical** — the single source of truth the whole system heals from |
| `agentic-fs-catalog` (DynamoDB) | The **derived index** of S3 — fast `list`/`glob`/`stat`; healable; first-class `catalog_only` |

Five tag-discoverable resources (`Project=agentic-fs`), so the entire footprint
is teardown-by-one-query — a design goal from day one, not an afterthought.
(IAM roles are tagged too but the Resource Groups Tagging API can't enumerate
IAM, so the live count via that API shows the four non-IAM resources + the
boundary policy.)

**All M1 stateful dependencies now exist** — CMK + data bucket + catalog — so the
serving layer (`compute_lambda`) can be built against real backends.

## How the infrastructure maps to the architecture

The component diagram (`agentic-fs-oss-plan.md` §2.2) decomposes into modules.
Status against each:

| Architecture component | Module(s) | Status | Why it exists (vision tie-in) |
|---|---|---|---|
| Deploy/CI/state/identity | `global/bootstrap`, `global/ci-roles`, `.github/workflows` | ✅ done | "Deploys into your AWS account" — and lets us iterate without blast radius |
| Data bucket (`tenants/`+`derived/`+`scratch/`) | `storage` | ✅ done | **S3 is canonical; everything else is derived and healable from it** (the load-bearing principle) |
| Encryption / tenancy floor | `kms` | ✅ done | **Multi-tenant, enterprise-secure by default** — SSE-KMS on every object |
| Catalog (list/glob/stat index) | `catalog_dynamodb` (default) / `catalog_postgres` | ✅ done | The **derived index** of S3 — navigation without O(corpus) S3 LISTs; healable; **swappable** |
| Serving compute (MCP+REST) | `compute_lambda` (default) / `compute_fargate` | ⏭️ **next** | **MCP-first, agent-shaped** — Function URL streaming + OAuth resource server + enforcement boundary |
| Ingest → extract → heal | `ingestion` | M2 | **S3 events drive a serverless pipeline**; the reconciler *is* "rebuildable from S3" |
| Semantic search (optional) | `search_bedrock_kb` | M3+ | **Grep is the floor; search is an accelerator you switch on** |
| OAuth IdP (optional) | `auth_cognito` | M1/opt | OAuth 2.1 resource server, batteries-included, $0 under free tier |
| Malware gate, audit, alarms | `security_guardduty`, `observability` | opt | Enterprise hardening — none of it bolted on later |

## Milestone roadmap

Each milestone is a **vertical slice** — infrastructure + the app code that uses
it — so the system is demoable at every step (plan §15).

- **Phase 0 — Guardrails** ✅ — state backend, OIDC plan/apply roles + permissions
  boundary, CI (validate → plan → gated sandbox apply → weekly drift), tflint +
  trivy gates, tagging, module/example scaffolds.
- **M0 — Foundation** ✅ — `kms` + `storage`. S3-is-canonical is now real.
- **M1 — Read path** 🔧 in progress — `catalog_dynamodb` ✅ done →
  `compute_lambda` (next) + dev auth → an agent can `list`/`read` a seeded corpus
  over MCP. *Exit:* Claude Desktop reads the corpus end-to-end.
- **M2 — Ingestion & extraction** — `ingestion` (EventBridge → SQS → Docling
  extractor → `derived/` + catalog rows) + the reconciler. *Exit:* a corrupt PDF
  lands `catalog_only` and is still cite-able; a hand-deleted catalog row heals.
- **M3 — Grep, scratch, budgets** — two-stage budgeted grep, scratch namespace,
  full MCP middleware (visibility, per-call enforcement, audit). *Exit:* an agent
  greps a 1k-file corpus under budget.
- **M4+ — Accelerators & hardening** — `search_bedrock_kb`, `auth_cognito`,
  `compute_fargate`/`network`, `observability`, `security_guardduty`; the
  `hardened`/`full`/`byo-postgres` example roots.

## How the pipeline keeps us safe as we add each piece

The Phase-0 work isn't scaffolding we move past — it's the rail every slice rides:

1. Branch off `master` → PR. CI runs `validate` (fmt/validate/tflint/trivy,
   credential-free + fork-safe) and a **read-only plan** that comments the exact
   diff.
2. Merge → the `apply` job assumes the **boundary-capped** apply role from the
   gated `sandbox` environment and applies only the quickstart root.
3. Weekly **drift** plan opens an issue if live AWS diverges from state.

Because the apply role is **PowerUser + permissions boundary** (not per-action
enumeration — see `terraform/DECISIONS.md` §2a), most milestones need **no
ci-roles change**. The one rule to remember: any module that creates an IAM role
(first: `compute_lambda` in M1) must set `permissions_boundary` to the
`permissions_boundary_arn` output, or the boundary denies its creation.

## Next wave: `compute_lambda` (the serving surface)

With the bucket + CMK + catalog in place, the next piece is the API/MCP serving
layer: an `agentic-fs-api` Lambda behind a streaming **Function URL**, its
execution role, and a log group. This is the **MCP-first** pillar made real — the
first thing an agent actually talks to.

Two things make this step distinct from M0/M1:

1. **First IAM-role-creating module.** The Lambda execution role is where the
   permissions-boundary rule first applies: the module takes a
   `permissions_boundary_arn` variable and sets it on the role, and the
   quickstart root threads the `ci-roles` `permissions_boundary_arn` output
   through. (Designed for — see `terraform/DECISIONS.md` §2a.)
2. **Needs a container image.** The real Lambda is the FastAPI/FastMCP app
   (`afs-server`), which doesn't exist yet. So there's a fork:
   - **(a) infra-complete, image-deferred** — build the full module against a
     placeholder image so it `plan`s/`apply`s now and is boundary-validated
     end-to-end; point it at the real image once the app lands. *Keeps the
     infra-first cadence.*
   - **(b) pivot to the app packages** (`afs-core` / `afs-server`) so there's a
     real image to deploy, then return and wire compute.

Recommendation: **(a)** — finish provisioning the serverless spine and prove the
boundary requirement, then swap in the real image. To be confirmed before we
start (brainstorm pending).
