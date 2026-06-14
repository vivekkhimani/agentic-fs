# ADR 0010: extraction routing — Haystack pipeline engine + rich rungs

**Status:** accepted · **Date:** 2026-06-14

## Context

Extraction today is a **linear ladder** ([ADR 0006](0006-extraction-normalizer-contract.md)):
the pipeline walks rungs in order and the first that `accepts` a document and clears
a **quality gate** (`min_chars_per_page`) wins; below-gate results fall through to the
next, heavier rung ([ADR 0009](0009-async-extraction-pipeline.md)). That gate already
gives us a cheap→expensive **cascade** — the cost-effective routing pattern the field
converges on (RouteLLM cascades; Unstructured's `fast → fall back to ocr_only`).

Two gaps surfaced testing real bespoke maritime documents (a TRO equipment drawing
and a 373-page trim & stability booklet):

- **Structure fidelity.** Textract's cheap `DetectDocumentText` flattens tables to a
  number-stream; `pdftables` (pdfplumber) reconstructs born-digital tables losslessly
  and for free; **drawings/diagrams** structure under neither — they need vision. To
  answer LLM queries correctly ("weight of item 34?") we must **preserve table
  structure**, and to make **diagrams** queryable we must **describe** them, which only
  a multimodal model does.
- **Routing.** A single linear ladder with a char-count gate can't express "born-digital
  PDF → `pdftables`; scanned PDF → OCR; image → vision; this rung found tables but
  couldn't structure them → escalate." We want users to configure **richer, branching
  pipelines** — but *without* hand-coded per-document rules, and *without* a per-document
  agentic loop (too expensive). Picking the extractor is explicitly a **consumer**
  concern; AFS's job is to offer good rungs and a configurable engine, not to guess.

## Decision

**Adopt [Haystack 2.x](https://haystack.deepset.ai) (`haystack-ai`) as the extraction
orchestration engine**, and grow the rung menu, while keeping S3-is-canonical and the
`Normalizer` authoring contract intact.

- **Haystack owns the graph.** The ladder becomes a Haystack pipeline: branching via
  `ConditionalRouter` (cascade / quality escalation) and `FileTypeRouter` (route by
  MIME), serializable to/from **YAML** so consumers configure complex pipelines
  declaratively. We use **`AsyncPipeline`** (Haystack 2.10+) so it composes with our
  async ingest path; rungs implement `run_async`.
- **`Normalizer` stays the rung unit.** Existing and third-party rungs are still authored
  against `afs_core.contracts.Normalizer` + the conformance kit; a thin **adapter** wraps
  each as a Haystack `@component`. The swap-guide promise ("bring your own parser") is
  unchanged — Haystack is the *wiring*, not the authoring surface.
- **Persistence stays ours.** `run_extraction` still owns the `derived/` writes and the
  catalog flip; the Haystack pipeline produces page text/structure, we persist it.
  Nothing about "rebuildable from S3" changes.
- **Routing is tiered and all consumer-configured** (no hard-coded rules, no mandatory
  LLM): (0) **quality-gate cascade** — enrich `QualityReport` so a rung self-reports
  `tables_detected_but_unstructured`, `figures_present`, `confidence`, and a router
  escalates on those; (1) **content-type routing** via `FileTypeRouter`; (2) **optional
  `llm_router`** first pass that returns *only an extractor name* (minimal output
  tokens), **size-gated** — it pays off only when routing-call cost ≪ the whole-doc cost
  difference between the right and wrong extractor (big docs yes, 1-pagers no).
- **New rungs/components** (each opt-in, license-clean):
  - `textract_analyze` — Textract **`AnalyzeDocument`** (the cheap `textract` =
    `DetectDocumentText` stays). Features configurable via `AFS_TEXTRACT_FEATURES`
    (`TABLES,LAYOUT,FORMS,QUERIES`): real markdown tables, reading order, key-value
    forms, and figure **markers** (Textract locates figures, never describes them).
  - `llm` — **batteries-included** multimodal extraction via the Anthropic and OpenAI
    Python SDKs' native document features (Claude PDF blocks ≤100 pp/32 MB; OpenAI file
    inputs ≤50 MB, text + page images). Provider-selectable; **describes diagrams/charts
    inline**, which is the only way to make figures queryable. Optional extras
    `[anthropic]` / `[openai]`; API keys via env/secrets.
  - *(optional)* an `unstructured` rung — its `auto` strategy self-routes fast/hi_res/
    ocr_only; a single do-everything OSS rung for users who don't want to tune a ladder.
- **Default behavior is unchanged.** The out-of-the-box pipeline is the current cascade
  (`text_native → pdf → docx`, `+textract` on the worker) expressed in Haystack; the
  rich rungs and branching are opt-in.
- **Dependency placement protects the slim serving image.** `haystack-ai` core is light
  (component deps are optional extras). The serving image loads only the lightweight
  inline components; the worker carries the heavy/branching ones. We measure the serving
  image delta during implementation; if it's material, serving keeps the direct
  lightweight ladder and Haystack runs only in the worker.

## Why

- **Cascade is the proven cost pattern** — most docs resolve on the cheap rung; we only
  pay for OCR/vision on what needs it. We already had it; Haystack lets us express richer
  escalation than a single char-count gate.
- **Haystack gives branching + YAML config + async for free** — we don't hand-roll a DAG
  engine, and users get a real, declarative interface for complex pipelines (the explicit
  goal). It's the established library for this; `farm-haystack` (1.x) is avoided.
- **The `Normalizer` contract survives** — our extension story, conformance kit, and
  swap-guides keep working; Haystack is additive wiring.
- **Figures become queryable** via the `llm` rung — solving the diagram problem Textract
  structurally cannot.
- **Consumers configure, AFS doesn't guess** — the engine + rungs are the product; the
  pipeline (which rung, what routing) is the user's declarative choice.

## Consequences

- **New dependency surface.** `haystack-ai` (light core) plus provider SDKs as optional
  extras. Haystack 2.x is evolving — **pin versions** and track the async API.
- **Migration work.** Existing rungs gain a Haystack-component adapter; the conformance
  kit gains an adapter test; the default ladder is re-expressed as a Haystack pipeline.
- **Two execution surfaces** to keep coherent: the lightweight inline path and the
  worker's full routing pipeline. Mitigated by config (same components, different YAML).
- **Cost + secrets for the `llm` rung** — per-document API spend and key handling; it's
  opt-in and best behind the size-gated router.
- **Serving image weight risk** — measured during build; escape hatch is worker-only
  Haystack (see Decision).
- **Net win:** user-configurable branching pipelines (YAML), structure-preserving and
  multimodal extraction, and queryable diagrams — without bespoke rules or per-doc agents.

## Alternatives considered

- **Home-grown light routing** (extend our own ladder config; integrate libraries only as
  rungs). Lighter, fully under our control, but a weaker user-facing config interface —
  we'd reinvent routers/serialization. *Rejected in favor of Haystack's mature, declarative
  engine.*
- **Keep the linear ladder.** Simplest, but can't express content-type/branch routing or
  carry table/figure/confidence signals — insufficient for the bespoke-document goal.
- **Per-document agentic orchestration.** Most flexible, but cost/latency are
  prohibitive; a single-shot size-gated router + cascade captures nearly all the benefit.
- **Unstructured as the engine.** It's a smart *extractor*, not an orchestrator — adopted
  as an optional rung instead.
