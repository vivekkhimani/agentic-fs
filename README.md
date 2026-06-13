# agentic-fs

**Filesystem-style access to your documents, for AI agents — in your own AWS
account.** `list` / `glob` / `grep` / ranged `read` / semantic `search` over
documents in **your S3**, exposed through **MCP** (and REST). Multi-tenant,
deploys with **one `terraform apply`**, ~**$2/month idle**, and **every stateful
layer is swappable**.

> **Status: early, in active development** (private repo for now; public OSS
> release + PyPI/module publishing are sequenced for the dogfood milestone — see
> [`docs/build-progress.md`](docs/build-progress.md)). The infra, contracts,
> stores, a read-path API + MCP mount are in place and the API is **deployed live
> on AWS Lambda**; ingestion is next. License: Apache-2.0 (intended).
> Background & rationale: [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md).

## Run it locally (5 minutes)

**Requirements:** [Docker](https://docs.docker.com/get-docker/) ·
[uv](https://docs.astral.sh/uv/getting-started/installation/) · `make`
(macOS: `xcode-select --install`).

```bash
git clone https://github.com/vivekkhimani/agentic-fs && cd agentic-fs
make dev          # builds the image, starts MinIO + DynamoDB Local + the API, seeds the bucket/table
curl localhost:8080/v1/healthz      # {"status":"ok","version":"..."}
curl localhost:8080/v1/me           # the local dev principal
curl "localhost:8080/v1/fs/handbook/entries"   # [] until you ingest documents (ingestion lands next)
```

`make down` stops it; `make clean` also wipes the volumes. The API is the same
container image that runs on AWS Lambda/Fargate — see
[ADR 0003](docs/decisions/0003-container-image.md).

> Local dev uses a **static dev principal** (`AFS_AUTH_MODE=dev`) — never run that
> in production; the OAuth resource server is a later slice.

## Develop

```bash
uv sync           # set up the Python workspace (once)
make test         # run the test suite
make lint         # ruff lint + format check
make fmt          # autoformat + autofix
make help         # list every target
```

CI gates every PR: **Python** (ruff + pytest) for `packages/**`, **Terraform**
(fmt/validate/tflint/trivy + a read-only plan) for `terraform/**`.

## Layout

```
packages/
  afs-core/      contracts (Protocols), DTOs, key scheme, conformance kits   (pydantic only)
  afs-server/    stores, services, the FastAPI app                            (implements afs-core)
terraform/       modular IaC — global state/CI roles, per-layer modules, examples
docs/            the plan, build progress, swap guides, decision records (ADRs)
Dockerfile       one image: Lambda + Fargate + local
```

## Swap any layer (plug-and-play)

Each stateful layer sits behind a small contract with a conformance kit and a
one-page guide — run it on the infrastructure you already have:

| Layer | Swap to | Guide |
|---|---|---|
| Object store | S3 · MinIO · **Cloudflare R2** · Wasabi · B2 (often just an endpoint) | [object-store](docs/swap-guides/object-store.md) |
| Catalog | DynamoDB · Postgres (BYO-RDS) | [catalog](docs/swap-guides/catalog.md) |
| Compute | Lambda · Fargate · Cloudflare Worker (edge) | [compute](docs/swap-guides/compute.md) |

How it works: a backend name in settings + entry-point discovery
([ADR 0002](docs/decisions/0002-pluggable-backends-via-entry-points.md)).

## Install (PyPI)

Install only the parts you need — the contracts are usable without the server.

| `pip install …` | You get | For |
|---|---|---|
| `afs-core` | contracts (Protocols), DTOs, key scheme, errors — **pydantic only** | building a custom store/connector against the contracts |
| `afs-core[testing]` | the above **+ conformance kits + in-memory fakes** (adds pytest) | certifying your implementation against the kits |
| `afs-server` | the service: stores (S3/DynamoDB), `FsService`, FastAPI app, MCP mount | running agentic-fs |

Distributions `afs-core` / `afs-server` import as `afs_core` / `afs_server`. Both
are PEP 561 typed. Packaging conventions, the namespace decision, and the
release/versioning flow are in
[ADR 0005](docs/decisions/0005-packaging-and-pypi-distribution.md);
releases publish to PyPI on a `vX.Y.Z` tag via Trusted Publishing
([`release.yml`](.github/workflows/release.yml)).

## Deploy to your AWS account

`terraform/` provisions the whole footprint (state backend, CI roles, the data
bucket, KMS, the catalog table, …) with per-layer modules and a `quickstart`
example. Start with [`terraform/README.md`](terraform/README.md). *(The serving
compute module + the live cloud deploy are in progress — see build-progress.)*

## Learn more

- [`docs/build-progress.md`](docs/build-progress.md) — what's built, what's next, the roadmap
- [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md) — the full design
- [`docs/swap-guides/`](docs/swap-guides/) · [`docs/decisions/`](docs/decisions/) — per-layer swaps & ADRs
