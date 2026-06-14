# Contributing to agentic-fs

Thanks for your interest in contributing! `agentic-fs` gives AI agents
filesystem-style access (`list` / `glob` / `grep` / ranged `read` / semantic
`search`) to documents in **your own** AWS account. This guide covers how to get
a dev environment running, the conventions we follow, and how to land a change.

> **Status:** early and in active development. Contracts, stores, the read-path
> API + MCP mount, and ingestion are evolving quickly. Open an issue before
> starting anything large so we can make sure it fits the roadmap
> ([`docs/build-progress.md`](docs/build-progress.md),
> [`docs/agentic-fs-oss-plan.md`](docs/agentic-fs-oss-plan.md)).

## Code of Conduct

This project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By
participating you are expected to uphold it. Report unacceptable behavior to
**vivekkhimani07@gmail.com**.

## Getting started

**Requirements:** [Docker](https://docs.docker.com/get-docker/),
[uv](https://docs.astral.sh/uv/getting-started/installation/), `make`, and (for
infra work) [Terraform](https://developer.hashicorp.com/terraform/install).

```bash
git clone https://github.com/vivekkhimani/agentic-fs && cd agentic-fs
uv sync                 # set up the Python workspace
uv run pre-commit install   # install the git hooks (lint, format, commit-msg)
make dev                # build the image, start MinIO + DynamoDB Local + the API, seed
curl localhost:8080/v1/healthz
```

`make down` stops the stack; `make clean` also wipes the volumes. Run `make help`
to see every target.

## Repository layout

The repo is a **uv workspace** with three distributable packages:

| Path | What lives here | Label |
| --- | --- | --- |
| `packages/afs-core/` | Contracts, models, conformance kits (deps: pydantic only) | `core` |
| `packages/afs-server/` | The FastAPI + FastMCP service, stores, extraction | `server` |
| `packages/afs-server/src/afs_server/extraction/` | Extraction rungs (textract, docling, tesseract, …) | `extractors` |
| `packages/afs-server/src/afs_server/mcp/` | MCP server, middleware, tools | `mcp` |
| `packages/afs-connector-sdk/` | `BaseConnector`, `IngestClient`, connector CLI | `connectors` |
| `terraform/` | Modules, examples, global state | `infra` |
| `docs/` | ADRs, build progress, swap guides | `docs` |
| `.github/` | CI workflows, issue/PR templates, labeler | `ci` |

PRs are auto-labeled by the files they touch (see
[`.github/labeler.yml`](.github/labeler.yml)).

## Development workflow

1. **Branch** off `master`. Use a descriptive prefix matching our convention:
   `feat/…`, `fix/…`, `docs/…`, `infra/…`, `test/…`, `chore/…`.
2. **Make your change** with tests. We use `pytest`; tests live in each
   package's `tests/` directory.
3. **Lint & test locally:**
   ```bash
   make fmt     # auto-format + autofix (ruff)
   make lint    # lint + format check
   make test    # run the Python suite
   ```
4. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/)
   (enforced by commitizen). Examples:
   - `feat(extraction): add llamaparse rung`
   - `fix(server): handle empty grep ranges`
   - `docs(adr): record search-backend decision`
5. **Open a PR** against `master`. Fill out the PR template, link the issue, and
   keep the change focused. CI must be green.

### Conventions

- **Python 3.12**, formatted and linted with [ruff](https://docs.astral.sh/ruff/).
- **GitHub Actions are pinned to commit SHAs** (with a `# vX.Y.Z` comment). When
  adding or bumping an action, pin the full SHA — don't use a floating tag.
- **`afs-core` has no server deps** and `afs-connector-sdk` has no server deps —
  keep those boundaries intact so the packages stay independently installable.
- **Versioning** is lockstep across the three packages via commitizen
  (`make bump`); contributors don't bump versions in PRs.
- Update docs (ADRs, `docs/build-progress.md`, README) when a change makes them
  out of date.

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/vivekkhimani/agentic-fs/issues/new/choose).
For anything security-related, **do not open a public issue** — see
[SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE), the same license that covers this project.
