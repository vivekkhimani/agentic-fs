# ADR 0012: extensible MCP tools + middleware (M3)

**Status:** accepted · **Date:** 2026-06-14

## Context

The MCP surface today hand-wires four read tools (`whoami`, `fs_list`, `fs_stat`,
`fs_read`) as `@mcp.tool` functions in `build_mcp`, under the dev principal, with
**no middleware** — the module docstring itself defers "per-connection auth,
claims-filtered `tools/list`, budgets, audit" and the remaining tools
(`fs_glob`/`fs_grep`/`scratch_*`) to "when their services land." M3 is that slice.

Two goals drive the design:

1. **Don't lock in the predefined tools.** The whole system is pluggable
   (stores, catalog, normalizers via [ADR 0002](0002-pluggable-backends-via-entry-points.md)
   entry-points). Tools should be too — adding a tool should be implement +
   register, not fork `build_mcp`. The platform gets more powerful as people add
   tools, and third parties extend it without us.
2. **`grep` is a headline verb** ("list / glob / grep / read / search") and isn't
   built. It must be **context-efficient** — an agent's window is the scarce
   resource. We take the proven shape from Chroma's ChromaFs write-up (virtual FS
   over existing infra; **two-stage grep**: coarse filter → regex on the subset),
   while skipping its Redis cache (we're stateless Lambda at ~$2/mo idle).

## Decision

### A pluggable tool registry + a uniform middleware chain

- **Tool contract** (`afs_core.contracts.Tool`, a Protocol): `name` (flat
  `snake_case`), a description (the docstring **is** the description), a Pydantic
  **params** model (→ JSON schema for `tools/list`), `required_scopes` /
  `required_capabilities`, and `async run(ctx, params) -> BaseModel`. Certified by
  a `ToolConformance` kit.
- **Registry**: builtins + `afs.tools` entry-points, resolved by name like the
  store/normalizer registries. A deployment chooses which tools are mounted.
- **The MCP mount wraps every tool** — builtin or plugin — in one chain, so a new
  tool inherits all of it for free:
  1. **Context/auth** — resolve the principal (dev now; OAuth resource server
     later, same seam).
  2. **Visibility** — `tools/list` is **claims-filtered**: a principal only sees
     tools whose `required_scopes`/`required_capabilities` it holds (and that its
     namespaces enable).
  3. **Per-call enforcement** — re-check scope/capability/namespace on invoke
     (visibility is UX; enforcement is the gate).
  4. **Budgets** — two layers so a tool can't blow the context window: each tool
     sets its own domain caps (max items/matches/context-lines), and the chain
     enforces a **uniform per-call output budget** (`AFS_TOOL_MAX_RESULT_BYTES`,
     256 KiB default) over the serialized result — a result over budget is
     **rejected** with a "narrow your query" error rather than truncated (keeps
     the payload structurally valid), so even a plugin tool with no caps of its
     own is bounded.
  5. **Audit** — structured log of `(principal, tool, args-summary, outcome)`
     (structlog, [ADR 0009 logging]).

### The M3 tools

- **`fs_grep`** — two-stage, budgeted. **Stage 1 (coarse filter):** the catalog
  narrows candidates by namespace + path prefix/glob (no full-corpus scan; the
  index is the in-memory tree). **Stage 2:** fetch the candidates' derived text
  and run the regex, emitting **bounded** results — capped files, capped
  matches/file, a few lines of surrounding context, a total byte budget, and a
  `next_cursor`/`truncated` signal. No Redis; rely on S3 read speed + the budget.
- **`fs_glob`** — wildcard path matching over the catalog (e.g. `**/*.pdf`),
  paginated.
- **`scratch_*`** — a per-principal read/write **workspace** (`scratch/<tenant>/
  <principal>/…`): `scratch_put` / `scratch_read` / `scratch_list` /
  `scratch_delete`, enforced by the catalog's **atomic** scratch quota
  (`adjust_scratch_usage`). The agent's place to stash intermediate work.

Tools call the shared service layer in-process (no HTTP self-calls), same as the
REST routes.

## Why

- **Extensible by construction** — tools are a registry + contract, so the surface
  grows without forking and third parties add tools that are first-class
  (enforced, audited, visible) automatically.
- **Enforcement is uniform, not per-tool** — wiring scope/budget/audit once in the
  chain means a new tool can't accidentally skip it; visibility + enforcement are
  separate (show only what you can use; still gate the call).
- **Context-efficiency is a budget, not a hope** — two-stage grep + hard output
  caps keep results inside the window; the catalog coarse-filter keeps it fast and
  cheap without a cache tier.
- **Same seams as the rest of the system** — entry-point registry (ADR 0002),
  shared services (no self-calls), structlog audit (ADR 0009).

## Consequences

- **The current `@mcp.tool` functions migrate** to the contract + registry; the
  four read tools become the first registry entries (behavior unchanged).
- **Budgets need sensible defaults** + per-call overrides; too tight frustrates
  agents, too loose risks the window. Start conservative, tune.
- **Visibility filtering needs the principal's claims at `tools/list`** — fine
  under dev auth; lands cleanly when the OAuth resource server replaces it.
- **No cross-call cache (v1)** — repeated grep over the same files re-reads S3.
  Acceptable at our scale; a Redis/edge cache is a later latency knob if needed.
- **Audit volume** — every tool call logs; structured + sampled if it gets noisy.

## Alternatives considered

- **Keep hand-wiring tools in `build_mcp`.** Simplest, but locks the surface to us
  and makes enforcement per-tool (easy to forget). Rejected — extensibility is a
  stated goal.
- **One-stage grep** (fetch all derived text, regex). Simple, but scans the whole
  corpus over the network and blows budgets on big namespaces. Rejected for the
  two-stage coarse-filter.
- **Add a Redis cache now** (as ChromaFs does). Real latency win for repeated
  grep, but adds an always-on dependency against the ~$2/mo idle promise. Deferred
  — revisit if grep latency becomes a problem.
- **Vector/semantic coarse-filter for grep** (Bedrock KB). Powerful, but that's
  the optional `search` accelerator (M4); grep's coarse filter is the catalog.
