# agentic-fs

**Filesystem-style access to your documents, for AI agents — in your own AWS
account.** `list` / `glob` / `grep` / `tree` / `find` / ranged `read` over your
documents in **your S3**, exposed through **MCP** (and REST). Multi-tenant,
deploys with **one `terraform apply`**, ~**$2/month idle**, and **every stateful
layer is swappable**.

> **Status: early, in active development** (private repo for now; public OSS
> release + PyPI/module publishing are being prepped — see
> [`docs/build-progress.md`](docs/build-progress.md)). The full loop is **live on
> AWS**: ingest → extract → catalog → the MCP/REST read surface, with scheduled
> heal-from-S3 and high-signal alarms. License: Apache-2.0 (intended).
> Background & rationale: [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md).

## What an agent gets

A bounded, scoped MCP tool surface that explores a document corpus the way a
coding agent explores a repo — but over extracted document text, indexed at
scale, multi-tenant, and remote:

- **Navigate** — `fs_list`, `fs_tree`, `fs_glob`, `fs_find` (by type / size / mtime / status)
- **Search** — `fs_grep` (two-stage, bounded, ripgrep-style filters)
- **Read** — `fs_read` (ranged, or by `section`), `fs_outline` (a doc's heading map), `fs_tables`, `fs_diff`
- **Work** — `scratch_*` (a per-principal workspace), `whoami`

Every tool runs through one middleware: claims-filtered visibility, scope
enforcement, a per-call output budget, and an audit log
([ADR 0012](docs/decisions/0012-mcp-tools-and-middleware.md)). Adding a tool is a
registry entry, not a fork. *(Semantic `fs_search` is an optional accelerator on
the roadmap — "grep is the floor.")*

## Run it locally (5 minutes)

**Requirements:** [Docker](https://docs.docker.com/get-docker/) ·
[uv](https://docs.astral.sh/uv/getting-started/installation/) · `make`
(macOS: `xcode-select --install`).

```bash
git clone https://github.com/vivekkhimani/agentic-fs && cd agentic-fs
make dev          # builds the image, starts MinIO + DynamoDB Local + the API, seeds the bucket/table
curl localhost:8080/v1/healthz      # {"status":"ok","version":"..."}
curl localhost:8080/v1/me           # the local dev principal

# Ingest a folder of documents, then read them back:
uv run fs-crawler --connector local --source ./docs --api-url http://localhost:8080 --namespace handbook
curl "localhost:8080/v1/fs/handbook/entries"   # the catalog rows that appeared
```

The **MCP** surface is mounted at `localhost:8080/mcp` — point any MCP client at
it. `make down` stops the stack; `make clean` also wipes the volumes. The API is
the same container image that runs on AWS Lambda/Fargate
([ADR 0003](docs/decisions/0003-container-image.md)).

> Local dev uses a **static dev principal** (`AFS_AUTH_MODE=dev`) — never in
> production. For production, agentic-fs is an OAuth 2.1 **resource server**:
> bring your own IdP (WorkOS/Cognito/Auth0/Okta/Keycloak), and `afs auth doctor`
> shows exactly how a token maps to a principal
> ([auth swap-guide](docs/swap-guides/auth.md), [ADR 0013](docs/decisions/0013-auth-oauth-resource-server.md)).

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
  afs-core/           contracts (Protocols), DTOs, key scheme, conformance kits   (pydantic only)
  afs-server/         stores, services, extraction, FastAPI app + MCP mount        (implements afs-core)
  afs-connector-sdk/  fs-crawler CLI + sync engine + Local FS / S3 / Drive / LlamaHub connectors
terraform/       modular IaC — global state/CI roles, per-layer modules, examples
docs/            the plan, build progress, swap guides, decision records (ADRs)
Dockerfile       one image: Lambda + Fargate + local
```

## Swap any layer (plug-and-play)

Each layer sits behind a small contract with a conformance kit and a one-page
guide — run it on the infrastructure you already have:

| Layer | Swap to | Guide |
|---|---|---|
| Object store | S3 · MinIO · R2 · Wasabi · B2 (endpoint) · **GCS / Azure / HDFS / local via fsspec** | [object-store](docs/swap-guides/object-store.md) |
| Catalog | DynamoDB · Postgres (BYO-RDS) | [catalog](docs/swap-guides/catalog.md) |
| Compute | Lambda · Fargate · Cloudflare Worker (edge) | [compute](docs/swap-guides/compute.md) |
| Extraction | text-native · **Docling** (PDF/Office/OCR) · Textract · your parser | [extraction](docs/swap-guides/extraction.md) |
| Connectors | Local FS · S3 · **Google Drive** · **LlamaHub (300+ readers)** | [connectors](docs/swap-guides/connectors.md) |
| Auth (IdP) | WorkOS · Cognito · Auth0 · Okta · Keycloak (BYO) | [auth](docs/swap-guides/auth.md) |
| MCP tools | add your own as `afs.tools` entry points | [tools](docs/swap-guides/tools.md) |

How it works: a backend name in settings + entry-point discovery
([ADR 0002](docs/decisions/0002-pluggable-backends-via-entry-points.md)).

## Install (PyPI)

Install only the parts you need — the contracts are usable without the server.

| `pip install …` | You get | For |
|---|---|---|
| `afs-core` | contracts (Protocols), DTOs, key scheme, errors — **pydantic only** | building a custom store/connector against the contracts |
| `afs-core[testing]` | the above **+ conformance kits + in-memory fakes** (adds pytest) | certifying your implementation against the kits |
| `afs-server` | the service: stores (S3/DynamoDB, `[fsspec]`), extraction, `FsService`, FastAPI app + MCP mount, the `afs` CLI | running agentic-fs |
| `afs-connector-sdk` | the `fs-crawler` CLI + sync engine + Local FS / S3 / Drive / LlamaHub connectors | crawling your documents in (`[aws]`/`[gdrive]`/`[llamahub]` per source) |

Distributions import as `afs_core` / `afs_server` / `afs_connector_sdk`. All
are PEP 561 typed. Packaging, the namespace decision, and the release flow are in
[ADR 0005](docs/decisions/0005-packaging-and-pypi-distribution.md);
releases publish to PyPI on a `vX.Y.Z` tag via Trusted Publishing
([`release.yml`](.github/workflows/release.yml)).

## Deploy to your AWS account

`terraform/` provisions the whole footprint with per-layer modules and a
`quickstart` example: state backend, CI roles, the data bucket + KMS, the catalog
table, the serving Lambda + Function URL, async ingestion (EventBridge → SQS →
worker), the scheduled reconciler, and high-signal CloudWatch alarms. One
`terraform apply`. Start with [`terraform/README.md`](terraform/README.md).

## Acknowledgments & prior art

agentic-fs stands on ideas others published first. The design is most directly
inspired by:

- **[Mintlify — How we built a virtual filesystem for our assistant](https://www.mintlify.com/blog/how-we-built-a-virtual-filesystem-for-our-assistant)** — the core shape: a virtual filesystem over existing storage, a claims-pruned path tree, **two-stage grep**, read-only semantics, and the sandbox cost framing.
- **[Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)** and **[Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)** — bounded, context-efficient tools and the MCP-first surface.
- **"Grep is the floor"** — [Claude Code dropped indexing for grep](https://vadim.blog/claude-code-no-indexing/) and [why grep beat embeddings (Augment)](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/); semantic search stays an opt-in accelerator.
- Ecosystem we build on: the **[Model Context Protocol](https://modelcontextprotocol.io)**, **[fsspec](https://filesystem-spec.readthedocs.io)** (the object-store adapter), **[LlamaHub/LlamaIndex](https://llamahub.ai/)** (the connector adapter), and **[Docling](https://github.com/DS4SD/docling)** (extraction).
- Adjacent prior art: [Turso AgentFS](https://github.com/tursodatabase/agentfs) · [Onyx](https://onyx.app) · [Ragie](https://www.ragie.ai).

Fuller reference list in [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md#references).

## Learn more

- [`docs/build-progress.md`](docs/build-progress.md) — what's built, what's next, the roadmap
- [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md) — the full design
- [`docs/swap-guides/`](docs/swap-guides/) · [`docs/decisions/`](docs/decisions/) — per-layer swaps & ADRs
