# Collaboration: agentic-fs ↔ obsidian-wiki

> Internal scoping note. Origin: Arnav (@Ar9av), maintainer of
> [obsidian-wiki](https://github.com/Ar9av/obsidian-wiki), commented on
> [issue #108](https://github.com/vivekkhimani/agentic-fs/issues/108) (OKF adoption).
> This file scopes what an open-source collaboration between the two projects could look like.

## The unifying thesis

Karpathy's [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):
compile knowledge into a persistent, cross-linked markdown wiki — **raw sources immutable, wiki
LLM-owned, schema as config** (`index.md` + `log.md` + `[[wikilinks]]` + YAML frontmatter;
ingest/query/lint workflows) — instead of re-deriving it via RAG on every query.

**Both projects descend from it:**

| | descends from Karpathy as… | strengths |
|---|---|---|
| **obsidian-wiki** | the *authoring / curation skill* (the agent that builds & maintains the vault) | local, single-user, agent-agnostic (Claude/Cursor/Codex/…); `.manifest.json` delta tracking; OKF as an export/import skin over a richer native schema |
| **agentic-fs** | the *secure shared substrate* the vault lives on | multi-tenant, OAuth 2.1, S3-canonical, bounded outputs, audit; pluggable Connector + Tool protocols; same anti-RAG creed ("grep is the floor; agentic navigation beats retrieval") |

agentic-fs's **"read-only corpora + per-principal scratch"** split mirrors Karpathy's
**"raw sources immutable / wiki LLM-owned."** OKF is the seam between the two halves.

## The four angles

### A. Obsidian-vault Connector for agentic-fs — *low risk · first artifact*
A `Connector` that discovers `.md` files in an Obsidian / obsidian-wiki vault and fetches their bytes,
frontmatter-aware, translation **at the boundary** (native vault untouched) — exactly the Phase 1/2
order Arnav recommended.
- Reuse `LocalConnector` (`packages/afs-connector-sdk/src/afs_connector_sdk/connectors/local.py`);
  skip `_raw/`; lift YAML frontmatter into `SourceItem` metadata → `CatalogEntry.metadata` + `title`.
  `fetch()` returns markdown; the `text_native` extraction rung passes it straight through.
- Incremental for free: obsidian-wiki's `.manifest.json` deltas → `IncrementalConnector.discover_changes(cursor)`
  (L2), with `SourceItem.version` L1 skip as floor.
- Register `[project.entry-points."afs.connectors"] obsidian = …`; certify via `ConnectorConformance`.
  ~100 lines.

### B. Jointly steward OKF + round-trip conformance suite — *the ecosystem play*
Co-own OKF; build a neutral corpus of golden bundles both tools ingest→emit losslessly.
- Fixture = (native frontmatter) + (expected OKF frontmatter) + (expected per-directory `index.md` —
  the part Arnav flagged as genuinely hard).
- Mapping under test: `title/category/tags/sources/created/updated/summary` ↔
  `type/title/description/resource/tags/timestamp`.
- Contract: ingest OKF → emit → diff == identity (modulo documented lossy fields).
- Home: start in agentic-fs `tests/fixtures/okf/`; graduate to a neutral
  `open-knowledge-format/conformance` repo other PKM tools can self-certify against.

### C. agentic-fs as a hosted / multi-tenant backend for obsidian-wiki — *strategic, longer-term*
obsidian-wiki's `wiki-query` / `wiki-context-pack` skills read a *remote* agentic-fs corpus over MCP;
teams share one vault, agentic-fs enforces who-sees-what. Karpathy's layers map: raw = read-only
corpora, wiki = writable namespace, schema = skill config.
- **Caveat:** agentic-fs is read-only corpora today (agents write only to scratch). Wiki authoring needs
  a first-class write path — the larger lift. North-star, not first PR.

### D. Wikilink / graph-aware MCP tools — *small, additive*
`fs_links` (resolve `[[wikilinks]]`) and `fs_graph` (backlinks/orphans/adjacency), built on the
doc-shape parsing in `fs_outline`/`fs_tables`. Karpathy's *lint* workflow becomes a tool surface.
Implement the `Tool` protocol (`afs_server/tools/base.py`); register `[project.entry-points."afs.tools"]`.

**Sequencing:** A + D first (low risk, match Arnav's advice) → B in parallel (shared standard) →
C as the strategic bet.

## Outreach
- `github-reply-108.md` — public reply to Arnav on #108 (review-only).
- `email-arnav.md` — concise/technical intro email (review-only; no public contact email confirmed —
  reach via [ar9av.in](https://ar9av.in) / GitHub / X @_ar9av).
- `okf-fixtures/` — seed round-trip conformance corpus for Angle B.
