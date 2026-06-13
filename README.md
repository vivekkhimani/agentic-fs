# agentic-fs

**Filesystem-style access to your documents, for AI agents — in your own AWS
account.** `list` / `glob` / `grep` / ranged `read` / semantic `search` over
documents in **your S3**, exposed through **MCP** (and REST). Multi-tenant,
deploys with **one `terraform apply`**, ~**$2/month idle**, and **every stateful
layer is swappable**.

> Status: **early, building in the open.** The infrastructure substrate and the
> contract layer are in place; the serving app is being assembled slice by slice.
> See [`docs/build-progress.md`](docs/build-progress.md) for exactly where we are.
> License: Apache-2.0.

## Why

The industry has converged on **agentic grep/read over a corpus** for insight
work. agentic-fs is the thin, opinionated layer between S3 and an agent —
tenancy, namespacing, authorization, a catalog, content search, and bounded
reads — the parts a raw "point an MCP server at a bucket" approach can't give you.
Full design: [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md).

## Repo layout

```
packages/
  afs-core/      contracts (Protocols), DTOs, the key scheme, conformance kits   (pydantic only)
  afs-server/    the service: stores, services, REST + MCP                        (implements afs-core)
terraform/       modular IaC — global state/CI roles, per-layer modules, examples
docs/            the plan, build progress, swap guides, and decision records (ADRs)
```

## Swap anything

Every stateful layer sits behind a small contract with a conformance kit and a
one-page swap guide — pick the infrastructure you already run:

- **Object store** — S3, or any S3-compatible service (MinIO, **Cloudflare R2**,
  Wasabi, B2) by setting one endpoint. [guide »](docs/swap-guides/object-store.md)
- *(more guides land with each layer: catalog, search, extraction, compute, IdP)*

The mechanism: a backend name in settings + entry-point discovery
([ADR 0002](docs/decisions/0002-pluggable-backends-via-entry-points.md)).

## Develop

```bash
# Python packages
uv sync
uv run pytest packages         # conformance kits run against in-memory + moto

# Infrastructure
cd terraform && terraform fmt -recursive .   # see terraform/README.md for the full flow
```

CI gates every PR: `Python` (ruff + pytest) for `packages/**`, `Terraform`
(fmt/validate/tflint/trivy + a read-only plan) for `terraform/**`.
