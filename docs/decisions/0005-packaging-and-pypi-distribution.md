# ADR 0005: packaging, PyPI distribution, and the import namespace

**Status:** accepted · **Date:** 2026-06-13

## Context

agentic-fs is a uv workspace (`packages/*`) with two distributable packages
today — `afs-core` (the contracts: Protocols, DTOs, key scheme, errors,
conformance kits) and `afs-server` (the service) — and a third, `afs-connector-sdk`,
planned but not yet built. A core design goal is that people install only what
they need: `pip install afs-core` to implement a custom store/connector against
the contracts and run the conformance kits, **without** pulling in the server,
FastAPI, boto3, etc. We need clean, idiomatic, publish-ready packaging and an
automated, token-less release to PyPI.

## Decision

### Distribution split

- **`afs-core`** — distribution `afs-core`, import name `afs_core`. Core
  dependency is **pydantic only**. The conformance kits + fakes
  (`afs_core.testing`) import `pytest` at module level, so they live behind an
  **`afs-core[testing]`** optional-dependency extra (`pytest`, `pytest-asyncio`).
  The top-level `afs_core.__init__` deliberately does **not** import `.testing`,
  so `import afs_core` / `.contracts` / `.models` / `.keys` / `.errors` work with
  no pytest installed (verified in CI/locally against the built wheel).
- **`afs-server`** — distribution `afs-server`, import name `afs_server`. Keeps
  `fastapi` / `uvicorn` / `boto3` / `fastmcp` / `pydantic-settings` as core deps
  (the service is not functional without them — they are not split). Empty,
  reserved extras `postgres` and `search` mark future backends (declared with a
  TODO; no phantom dependencies).

### Namespace: keep distinct top-levels (`afs_core`, `afs_server`)

We **keep the current distinct import top-levels** rather than adopting a PEP 420
implicit-namespace `afs.` layout (`afs.core`, `afs.server`).

**Why.** `foo-core` / `foo-server` distributions exposing `foo_core` / `foo_server`
import names is a perfectly idiomatic, widely-used pattern (e.g. many SDK + plugin
ecosystems). PEP 420 namespaces buy us nothing here: there is no shared `afs`
runtime surface to unify, both packages already install and import independently,
and the conformance/registry imports are explicit. Switching to `afs.core` would
require a repo-wide import-renaming refactor (every module, test, entry-point
group, `known-first-party`, and ruff config) for no functional gain, and namespace
packages add real footguns (a stray `afs/__init__.py` shadows the namespace; tools
and `py.typed` discovery get subtler). Per the maintainer's "don't over-engineer"
constraint, the distinct top-levels stay.

### Typing (PEP 561)

Each package ships a **`py.typed`** marker at `src/<pkg>/py.typed`, included in the
wheel by hatchling's default file inclusion (verified: both wheels contain
`<pkg>/py.typed`), plus the `Typing :: Typed` Trove classifier. Adopters get the
inline types.

### Versioning

Lockstep **`0.1.0`** across both packages for now. Each package's `version` in its
`pyproject.toml` is the **single source of truth**. Releases are cut by pushing a
**`vX.Y.Z`** git tag; the release workflow refuses to publish unless the tag
(minus the `v`) equals the version in **both** pyprojects. Bump the pyprojects in
the same commit that you tag.

### Release automation (token-less)

`.github/workflows/release.yml` builds **both** packages with `uv build` and
publishes with `uv publish` via **PyPI Trusted Publishing (OIDC)** — no API
tokens or secrets:

- **`v*.*.*` tag push** → publish to **PyPI** (environment `pypi`).
- **`workflow_dispatch`** → publish to **TestPyPI** (environment `testpypi`) for
  dry-run rehearsals.

Every third-party action is SHA-pinned with a `# vX.Y.Z` comment, matching the
repo's other workflows. The publish jobs request `id-token: write`; `uv publish
--trusted-publishing always` exchanges the GitHub OIDC token for an index token
at publish time.

## Consequences

- Adopters can `pip install afs-core` (contracts only), `afs-core[testing]` (+
  conformance kit), or `afs-server` (the service), as documented in the root
  README install matrix.
- The maintainer must configure a **Trusted Publisher** on pypi.org (and
  test.pypi.org for dry-runs) before the first release — publisher = GitHub,
  repo `vivekkhimani/agentic-fs`, workflow `release.yml`, environment `pypi`
  (resp. `testpypi`). Trusted publishing works from a private repo.
- When `afs-connector-sdk` is built it follows the same conventions (distribution
  `afs-connector-sdk`, import `afs_connector_sdk`, `py.typed`, added to
  `release.yml`).
- Moving off lockstep versioning later (independent per-package versions) means
  changing the tag→version convention; revisit then.
