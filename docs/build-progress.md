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
serving layer can be built against real backends.

### Application track (local-first, no AWS deploy yet)

| Package | What's in it | Tests |
|---|---|---|
| `afs-core` | the contracts (`ObjectStore`/`CatalogStore` Protocols), DTOs, the key scheme, the closed error vocabulary, and the **conformance kits** | 50 |
| `afs-server` | `settings`, the **pluggable store registry**, `S3ObjectStore` + `DynamoDBCatalogStore` (moto-certified), the **`FsService` read path**, a **FastAPI app** (`/v1/healthz` · `/readyz` · `/me` · `fs/{ns}/{entries,stat,doc}`), and an **MCP mount** at `/mcp` (`whoami` · `fs_list` · `fs_stat` · `fs_read` over the same `FsService`, in-process) | +41 |

The API is **containerized** ([`Dockerfile`](../Dockerfile), [ADR 0003](decisions/0003-container-image.md)):
one multi-stage, non-root, ~190 MB image runs uvicorn on **Lambda (Web Adapter) +
Fargate + locally** — verified to build and serve `/v1/healthz`. `make dev` runs
it against MinIO + DynamoDB Local.

**Both stores done.** Swap-ability is real and demonstrated:
- object store — the S3 store *is* the store for any S3-compatible endpoint
  (MinIO, Cloudflare R2, Wasabi, B2) via one env var
  ([swap guide](swap-guides/object-store.md)).
- catalog store — `DynamoDBCatalogStore` over the single-table schema; another
  backend (e.g. Postgres) is implement → certify → register
  ([swap guide](swap-guides/catalog.md)).

Both proven by the *same* conformance kit that certifies the in-memory fakes
([ADR 0002](decisions/0002-pluggable-backends-via-entry-points.md)).

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

## The runway to "image + AWS"

We build and test **locally first**; the container image + AWS deploy is the last
step of the read path, when the app actually serves requests — no premature shell.

```
✅ afs-core foundations (keys/errors/models)
✅ afs-core contracts + conformance kits
✅ afs-server: settings + store registry + S3 ObjectStore (moto-certified)
✅ afs-server: DynamoDB CatalogStore (certified by the same kit)
✅ afs-server: FsService read path + FastAPI app + Dockerfile + docker-compose
✅ afs-server: MCP mount at /mcp (whoami/fs_list/fs_stat/fs_read, shared FsService)
✅ ecr_mirror + compute_lambda + image CD (image.yml: build/push/roll on merge)
✅ DEPLOYED — API LIVE on Lambda + Function URL (AWS_IAM); healthz/readyz/me/entries
      verified via SigV4. readyz=ok ⇒ the Lambda reached DynamoDB through its
      least-priv, boundary-bound exec role. The whole AWS path works end-to-end.
⏭️ ingestion + extraction → documents actually land and become readable          ← next
      (the live API answers, but the corpus is empty until ingestion)
```

When `compute_lambda` lands it is the **first IAM-role-creating module**, so it
takes a `permissions_boundary_arn` and sets it on the Lambda exec role, threaded
from the `ci-roles` output (the boundary's escalation-prevention deny enforces it
— `terraform/DECISIONS.md` §2a).

## Remaining docket (roadmap)

**Product — toward a demoable v1:**

- **Ingestion & extraction (M2)** *(next)* — the write path (upload intent → S3 →
  catalog row), event-driven cataloger + extractor (Docling), `catalog_only`
  degradation, the reconciler, and the connector SDK + `fs-crawler`. *The biggest
  unlock — makes the corpus non-empty so `fs_list`/`fs_read` return real docs.*
- **Grep, scratch, budgets (M3)** — two-stage grep, glob, the scratch namespace,
  and the full MCP middleware (per-call enforcement, budgets, audit log).
- **OAuth 2.1 resource server** (+ `auth_cognito`) — replaces dev-auth; required
  for real multi-tenant and to safely set the Function URL to `NONE`/public.

**Platform / enablers:**

- **OpenAPI export + `x-mcp-tool` extensions** + codegen drift-gate → unblocks
  typed clients, the edge Worker, and the Speakeasy evaluation.
- `search_bedrock_kb` (optional semantic), `observability` (alarms/dashboard),
  `catalog_postgres` (proves the catalog swap for real), `compute_fargate` +
  `network`, and the `hardened`/`full` example roots.

**Release / consumption plumbing** (prerequisites for the dogfood consumer repo):

- **Package release** — `release.yml`: `uv build` the three packages → PyPI, with
  versioned tags.
- **Image publishing** — publish `agentic-fs-api` to a public registry (GHCR /
  public ECR) so consumers can mirror it into their own account.
- **Externally-consumable Terraform modules** — see the distribution note below.

## Deferred / to investigate

Tracked here so they aren't lost — intentionally *not* built yet.

- **`compute_fargate` + `network` (alternate compute)** — the same image behind
  an ALB on ECS for always-on / no-cold-start / OCR-at-scale. Deferred to the
  **"release configs" milestone** (alongside the `hardened`/`full` example roots):
  it pulls in a VPC + ALB + ECS service (~$36+/mo while up, real teardown), and
  the default Lambda path already proves the image runs. Implement it as a
  deliberate config option for the OSS release, not a throwaway test now.
- **MCP edge Worker (Cloudflare)** — optional edge layer that terminates MCP +
  OAuth and calls the REST data plane (plan §7.1; `docs/swap-guides/compute.md`).
  **Deferred on purpose:** its client + tools table are *generated* from
  `schemas/openapi.json` + the `x-mcp-tool` route extensions, and the primary MCP
  surface is the in-process Python mount — none of which exist yet. Building it
  earlier means hand-stubbed, throwaway code plus a premature Node/wrangler
  toolchain. Sequence: Python MCP mount → OpenAPI export + `x-mcp-tool` → *then*
  scaffold `workers/mcp-edge/` (generate, don't hand-write) and deploy via
  Wrangler.

- **Codegen for the MCP/SDK surface — evaluate [Speakeasy](https://www.speakeasy.com/).**
  The plan hand-rolls the generation pipeline (`openapi-typescript` for the client
  + a custom emitter for the tools table from `x-mcp-tool` / `x-required-scopes`,
  plan §7.1, §12). Speakeasy generates **SDKs and an MCP server directly from an
  OpenAPI spec**, which overlaps heavily with what we'd otherwise build by hand.
  **Evaluate once the OpenAPI export lands** — if it covers the MCP-tool +
  scopes mapping, it could replace the custom `gen:client` / `gen:tools` step (and
  may subsume the edge-Worker codegen too). Decide via an ADR at that point.

- **Dogfood via a separate consumer repo (BYO-AWS validation).** The whole pitch
  is "deploy into *your* account: `pip install` + `terraform apply`." A second
  repo that consumes our published packages + tagged Terraform modules + mirrored
  image — deploying agentic-fs into its own account and ingesting/reading docs —
  is the real proof. **Sequencing:** keep building the product here (fast
  monorepo iteration); do the release plumbing in parallel; stand up a *thin*
  deploy-only dogfood as soon as packages/image/modules publish; do the *full*
  dogfood after ingestion; **then tear down this maintainer sandbox via the
  `Project=agentic-fs` tag** (which also validates the teardown story). Two
  consumption surfaces with different friction: the **Python packages** (easy once
  published) and the **Terraform modules**, which need (1) tagged module refs,
  (2) decoupling from monorepo specifics (`compute_lambda` currently reads *our*
  `ci-roles` boundary from remote state, and the boundary is *required* — must
  become **optional** for external roots, plus a monorepo-free `quickstart`
  variant), and (3) **image distribution**: Lambda pulls only from same-account
  ECR, so the consumer flow is *publish image publicly → their `ecr_mirror` copies
  it into their ECR → their `compute_lambda` points at the copy* (the "mirror"
  half of `ecr_mirror`, currently deferred, becomes a prerequisite).

- **Distribution & repo visibility (no rush — sequence with the consumer repo).**
  - Publishing to **PyPI works from a private repo** (OIDC trusted publishing; the
    source stays private). *But a pypi.org package is public* — anyone can install
    and read the wheel. Truly-private packages would need a private index (AWS
    CodeArtifact), not pypi.org.
  - **We don't need the repo public for PyPI**, but we *do* for frictionless
    Terraform `git::` module sources (a private repo forces consumers' CI to carry
    a deploy key/PAT). Public = anonymous.
  - **Pre-public cleanup (decision: do it as the "make it consumable" slice, not
    now):** parameterize the hardcoded account ID `002988089284` (it's baked into
    ci-roles/bootstrap defaults, the backend blocks, `quickstart`, the README, and
    the `AWS_ACCOUNT_ID` secret) into variables/placeholders; decouple the
    monorepo-specific CI. Account IDs aren't *secret*, but hardcoding the
    maintainer's sandbox throughout an OSS template is poor hygiene.
  - **Recommendation:** keep developing privately; do the parameterization +
    visibility flip as a deliberate slice when wiring the consumer repo. Until
    then, **avoid adding new account-ID / monorepo coupling.** Promote this to a
    proper ADR (`docs/decisions/`) when we commit to the public timeline.
