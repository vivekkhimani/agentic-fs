# ADR 0006: extraction is a pluggable `Normalizer` contract, not pipeline code

**Status:** accepted · **Date:** 2026-06-13

## Context

Document parsing varies wildly (plain text, PDF/Office via Docling, OCR,
LlamaParse, bespoke parsers). It must be swappable and community-extensible, and
it must **not** be coupled into the ingestion pipeline. The first ingestion slice
parsed `text_native` *inline* inside `IngestService` — exactly the coupling to
avoid.

## Decision

Extraction lives behind a contract, with three clean responsibilities:

- **`Normalizer`** (`afs_core.contracts.normalize`) — *bytes → pages*. Takes a
  `SourceDocument` (the original staged to a file) and returns a
  `NormalizedDocument` (per-page markdown + a `QualityReport`), or raises
  `NormalizationError(reason)`. It never touches S3 keys or catalog rows.
- **`ExtractionPipeline`** (afs-server) — *orchestration*. Orders normalizers into
  a **ladder**, applies a quality gate, escalates to the next rung, and degrades
  to `catalog_only` when no rung succeeds.
- **Ingestion pipeline** — *where bytes land* (S3 keys, catalog rows, derived
  layout). It calls the `ExtractionPipeline`; it does not parse.

Normalizers are selected by name (builtins + the `afs.normalizers` entry-point
group) and certified by `afs_core.testing.NormalizerConformance`. `text_native`
is the first builtin rung; `docling`/`llamaparse`/your-own are added rungs with
**zero pipeline changes**.

In production, extraction runs **asynchronously** in the event-driven extractor
worker (S3 event → SQS → the same pipeline) so heavy parsers don't block ingest;
the current slice runs it inline in-request (and locally) for a faithful loop.

## Why

- **Clean boundary** — a parser author thinks only "bytes → markdown pages"; the
  pipeline owns quality/escalation/degradation; ingestion owns storage.
- **Community extensibility** — "want a different parser? write a `Normalizer`,
  certify it, register it, name it in the ladder." No fork (the project's core
  pluggability pitch, applied to extraction).
- **Right execution model** — async/decoupled so Docling/OCR throughput is queue
  depth, not request latency; the `Normalizer` stays a clean per-document unit.

## Consequences

- The inline `text_native` shortcut is paid down — it's now a registered rung.
- The in-request execution is a stepping stone to the SQS-driven extractor worker
  (a later slice, with the ingestion module's queue infra).
