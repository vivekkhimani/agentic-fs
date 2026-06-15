# ADR 0014: adopt connector/extraction ecosystems via adapters, not as the core

**Status:** accepted · **Date:** 2026-06-14

## Context

Before open-sourcing (goal: **adoption, ease of use, ecosystem growth**) we asked
whether to drop our own connector model in favour of an existing open-source
standard — Airbyte/Singer (ELT), LlamaIndex/LangChain document loaders, Docling
(parsing) — so contributors reuse familiar tools and we maintain less.

Evaluating the landscape, the named tools sit at **three different layers**, none
of which is the layer agentic-fs occupies:

| Layer | Does | Examples | Fit |
|---|---|---|---|
| Sync / ELT | move **records** source→warehouse, incrementally | Airbyte (own protocol), Singer/Meltano | Poor — row-oriented + heavy runtime; wrong shape for "files → S3 + RAG" |
| Document loaders | source → in-memory `Document(text, metadata)` | LlamaHub `BaseReader` (300+), LangChain `BaseLoader` | Good — document-shaped, in-process, huge catalog |
| Parsing / extraction | bytes → structured text/tables | Docling, unstructured.io | Already ours (`Normalizer`, ADR 0006; Docling is a rung) |
| **Serving substrate** ← us | canonical S3 + healable catalog + MCP grep/glob/read/search + multi-tenant auth | — | **No OSS spec covers this — our differentiator** |

Facts that shaped the call: **Airbyte is not built on Singer** (compatible only);
**Singer has no central enforcement**, so taps aren't guaranteed mutually
compatible; **LlamaHub is ~300+ readers** now folded into core `llama-index`.

So "just settle on these instead of our own" isn't actually on the table — they
don't occupy our layer. The real, narrower question: at the **input** and
**parsing** *edges*, do we adopt these ecosystems or hand-roll each integration?

## Decision

**Keep our thin `Connector`/`Normalizer` Protocols as the stable internal seam,
and tie the big ecosystems in behind them via adapters** — the entry-point
pluggability pattern we already use ([ADR 0002](0002-pluggable-backends-via-entry-points.md)).
We do **not** replace our model, and we do **not** hand-roll 300 connectors.

In priority order:

1. **`LlamaHub reader → Connector` adapter (highest leverage).** One bridge turns
   the **300+ community readers** (SharePoint, Confluence, Notion, Slack, Drive…)
   into agentic-fs sources, and lets contributors add sources in a framework they
   already know. Mechanics: a reader produces `Document(text, metadata)` — i.e.
   it is a loader that has *already extracted*. The adapter is a **pre-extracted
   connector**: `discover()` runs the reader and maps each `Document` to a
   `SourceItem` (path from metadata; `locator` = the doc id); `fetch()` returns
   `document.text` as `text/markdown` bytes. That flows through the **existing**
   ingest path unchanged — the `text_native` rung passes the text through to
   derived text, a catalog row appears, and grep/read/glob just work. **Zero core
   change.** Reader metadata is carried as provenance.
   - Trade-off (documented): we ingest the reader's *extracted text*, not the
     original bytes, so there's no later re-extraction with a richer rung. That's
     the right call for the long tail of sources where a reader already exists;
     our native raw-bytes connectors (local/s3/drive) remain for sources where we
     want the original in S3 + our own extraction ladder.
2. **`fsspec → ObjectStore` adapter** (storage edge, already on the roadmap): one
   adapter certifies the store contract against GCS / Azure Blob / HDFS / local.
3. **Extraction stays ours**, ecosystem-friendly: Docling is already a `Normalizer`
   rung; an `unstructured.io` rung can be added the same way if demanded.
4. **No Airbyte/Singer as a core dependency.** Wrong shape (record ELT, not
   files-for-RAG) and a heavy platform. A user who lives in Airbyte lands files in
   S3 and our S3 connector ingests them — interop without coupling.

Adapters ship as **optional extras / packages** (`afs-connector-sdk[llamahub]`
pulling the relevant `llama-index-readers-*`), so the core stays lean and the
adapter is certified by the same `ConnectorConformance` kit as any connector.

## Why

- **Ecosystem without lock-in.** A thin contract + adapters taps 300+ sources now
  while keeping us free of any one framework's protocol, roadmap, or breaking
  changes — and lets us bridge several (LlamaHub now, Airbyte-via-S3, raw later)
  behind one seam. Betting the core on Singer (no compat guarantees) or Airbyte
  (heavy, record-shaped) would be the riskier path.
- **Protects the differentiator.** The serving substrate is the part no framework
  provides; keep it first-class and let the commodity edges (fetch bytes, parse)
  be pluggable.
- **Maximises adoption *and* simplicity** — the stated goal: contributors plug in
  a reader they already wrote; we maintain one adapter, not hundreds of connectors.
- **Same seams as everything else** — entry-point registry (ADR 0002), shared
  service layer, conformance kits.

## Consequences

- **Reorders the connector docket:** the `LlamaHub` adapter slots *ahead of* the
  hand-written SharePoint connector — the adapter delivers SharePoint *and*
  hundreds more in one change.
- A new optional extra (`[llamahub]`) and a small `_LlamaHubConnector` adapter +
  its conformance run; core deps unchanged.
- Pre-extracted ingest is a documented mode (reader text becomes the canonical
  `text/markdown` content); native raw-bytes connectors stay the path when the
  original + our extraction ladder are wanted.
- Future, additive: expose select readers/parsers as `Normalizer` rungs too;
  an Airbyte-source bridge only if real demand appears.

## References

- [Airbyte: why Airbyte is not built on Singer](https://airbyte.com/blog/airbyte-vs-singer-why-airbyte-is-not-built-on-top-of-singer)
  · Singer compatibility caveats (HN).
- [LlamaHub](https://llamahub.ai/) · [llama-hub repo](https://github.com/run-llama/llama-hub) (readers usable from LlamaIndex *and* LangChain).
- [ADR 0007](0007-connector-model.md) (the `Connector`/`SyncEngine` model),
  [ADR 0006](0006-extraction-normalizer-contract.md) (the `Normalizer` ladder, Docling),
  [ADR 0002](0002-pluggable-backends-via-entry-points.md) (entry-point pluggability).
