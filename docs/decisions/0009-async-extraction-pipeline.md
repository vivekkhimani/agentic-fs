# ADR 0009: extraction runs async, driven by S3 events

**Status:** accepted · **Date:** 2026-06-14

## Context

Heavy parsers (Docling = torch + models) are too big for the lean serving image
and too slow for the request path, and a large connector crawl shouldn't be able
to block or time out the API. Extraction must be **decoupled** from ingest. The
vision is explicit: *"S3 events drive a serverless pipeline; the reconciler is
'rebuildable from S3'."*

## Decision

Extraction is an **asynchronous, S3-event-driven** stage.

- **Ingest is two-phase.** `PUT` stores the bytes to S3 and writes a `pending`
  catalog row, then returns immediately. Nothing is parsed in the request.
- **An S3 event drives the worker.** EventBridge fires on object-created under
  `tenants/` → **SQS** (+ DLQ) → an **extractor worker Lambda** running its own
  **parametric** image (`Dockerfile.worker`, `AFS_EXTRAS` build arg). The slim
  default ships `textract` (managed OCR, no torch); `docling` and other heavy
  rungs are opt-in builds. The worker runs the same `ExtractionPipeline`, writes
  the `derived/` pages, and flips the catalog row to `extracted` / `catalog_only`.
- **The worker is the single extraction authority and it upserts from S3.** It
  reverses the object key (`keys.parse_key`) to `tenant/namespace/path`, so an
  object dropped *directly* into the bucket (`aws s3 sync`, a bulk load — bypassing
  the API entirely) still gets indexed, and re-driving extraction is just
  re-processing the object. This is the "rebuildable from S3" property.
- **`AFS_EXTRACTION_MODE`** (`inline` | `async`) selects the behavior. `inline`
  keeps the synchronous in-request path (text_native, no extra infra — local dev
  and tiny deployments); the deployed worker environment runs `async`. Default is
  `inline` so nothing changes until the worker infrastructure is live.

## Why

- **Heavy parsers off the request path** — Docling/OCR never block ingest; the
  serving image stays ~190 MB, and the worker image is sized to its rungs (~700 MB
  for the managed-OCR default; ML deps only in an opt-in docling build).
- **Ingest can't time out** — a 10k-file crawl just drops `pending` rows fast; the
  queue absorbs the extraction load and scales independently.
- **Heal + bulk-load for free** — anything in S3 gets extracted, so the reconciler
  (next) heals by re-driving events, and users can bulk-drop into the bucket.

## Consequences

- **Eventual consistency** — a document is briefly unreadable after `PUT` (it's
  `pending` until the worker runs, ~seconds). Acceptable for the agent-document
  use case; the `pending` state is explicit in the catalog.
- **At-least-once delivery** — SQS may redeliver, so the worker is **idempotent**:
  derived keys are deterministic (`entry_id` + page), so re-extraction overwrites
  rather than duplicates. Poison messages land in the DLQ.

## Alternatives considered

- **API-enqueues to SQS** (no EventBridge) — simpler IAM, but loses "any object in
  S3 gets extracted" (bulk drops + heal would have to go through the API).
- **Hybrid: inline text + async heavy** — zero-delay for text, but two extraction
  triggers and de-dup logic; rejected for a single clean path. (Lightweight
  *inline* PDF/docx rungs are a separate, complementary backlog item — they make
  more types readable synchronously without changing this async model.)
