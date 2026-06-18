# ADR 0015: read-path performance — concurrency, a linear-time regex engine, deferred cache

**Status:** accepted · **Date:** 2026-06-18

## Context

[ADR 0012](0012-mcp-tools-and-middleware.md) shipped the read tools (`fs_read`,
`fs_grep`, `fs_outline`, `fs_tables`, `fs_diff`, …) with a deliberate stance:
**two-stage, budgeted, no cache** — "rely on S3 read speed + the budget," with a
Redis tier explicitly deferred ("revisit if grep latency becomes a problem").
Making the surface **production-ready** forces that revisit. A close read of
`FsService` surfaced four issues, none of which the cache tier addresses:

1. **Serial per-page S3 GETs are the bottleneck — not the regex.** Derived text
   is stored one object per page (`keys.derived_text_key`). Every text tool walks
   `for page in …: raw = await self._objects.get(key)` — each a blocking boto3
   call (`asyncio.to_thread`, [ADR 0001](0001-boto3-sync-to-thread.md)) **awaited
   one at a time**. Worst-case `fs_grep` at the default budgets is
   `MAX_GREP_FILES` (200) docs × pages-per-doc ≈ **hundreds–thousands of serial
   round-trips**, governed only by the 5 MB byte budget. At ~20–40 ms/GET that is
   tens of seconds of wall-clock that is **almost entirely network wait** — the
   CPU scan of 5 MB through Python `re` is tens of ms by comparison.

2. **`fs_grep` can silently under-report.** `_match_entries` caps candidates at
   `max_files` by path sort order and returns **no signal** that more matched;
   `grep` only sets `truncated` on a *stage-2* (matches/bytes) budget. On a large
   namespace with the default `path_glob="*"`, grep scans the first 200 docs and
   can return `truncated: false` having looked at a fraction of the corpus — an
   agent reasonably concludes "no matches exist." This is a correctness-of-signal
   bug, independent of latency.

3. **Untrusted regex on Python `re` is a ReDoS exposure.** We hand arbitrary
   agent/user patterns straight to `re` and run them per line. A pattern like
   `(a+)+$` can pin a CPU and stall the request. CPython has no clean per-match
   timeout, so this is hard to bound after the fact.

4. **No literal fast-path.** A plain-string query (`"invoice"`) still compiles and
   runs the regex engine over every line of every page, including pages that
   cannot possibly contain it.

The Mintlify/ChromaFs write-up that inspired ADR 0012 pairs the two-stage filter
with a **Redis prefetch tier**; we dropped the cache to hold the "~$2/mo idle,
stateless Lambda" promise. The insight here is that **most of their win is
bulk/parallel candidate fetch + in-memory scan, which we can adopt with no new
infrastructure** — the standing cache is a separate, later latency knob.

We evaluated and rejected two "use real grep" shortcuts as the *primary* fix:

- **Shell out to `ripgrep`** (download candidates to `/tmp`, run `rg`). It does
  **not** remove the bottleneck — the same N S3 GETs are still required to get
  bytes local — and it adds a binary, subprocess/temp-file management, `--json`
  parsing, and a regex-dialect shift. Its real merits (linear-time regex,
  ripgrep flags) are obtainable more cheaply (below).
- **A pre-warmed worker "with access to all files."** That is always-on compute
  (the Fargate path, #73) and, at "all files," a multi-tenant data-colocation
  problem. The defensible version is a cache of *hot* files — i.e. the deferred
  cache tier (#78), not a new always-on box. `fs_grep` is also a *synchronous*
  read serving the agent; offloading it to our async extraction worker would add
  latency, not remove it.

## Decision

Treat read-path performance as three phases. Phase 1 is infra-free and lands
first; Phase 2 is a contained engine swap; Phase 3 stays opt-in so ADR 0012's
idle-cost promise holds.

### Phase 1 — concurrency + correctness (no new infra)

- **Concurrent, bounded page fetch.** A shared `FsService._get_pages` helper
  fetches a document's page objects with `asyncio.gather` under a bounded
  semaphore (`PAGE_FETCH_CONCURRENCY`). Used by `fs_read`, `fs_outline`,
  `fs_tables` (bounded page caps) and, **chunked**, by `fs_grep` so the byte
  budget still stops the scan early. `fs_diff` inherits it via `fs_read`. The
  `to_thread` GETs already release the GIL on network I/O, so this is a
  near-linear latency win.
- **Honest grep truncation.** `_match_entries` returns whether the candidate cap
  was hit; `fs_grep` folds that into `truncated`, so a capped stage-1 is reported
  even when no stage-2 budget trips.
- **Literal page prefilter.** When `pattern` is a literal (`re.escape(pattern) ==
  pattern`), skip `splitlines()` + per-line regex on any page whose (case-folded)
  text doesn't contain the needle. A pure optimization — it cannot change which
  lines match; it only skips pages that provably can't match.

### Phase 2 — a linear-time regex engine + ripgrep-parity flags

- Swap the scan engine from `re` to **RE2** (`google-re2`). RE2 is linear-time by
  construction — **no catastrophic backtracking**, the same guarantee that makes
  ripgrep safe — but it is an **in-process library**, so no subprocess, temp
  files, or bundled binary. This closes the ReDoS exposure (#3) on untrusted
  patterns. RE2's dialect drops lookaround/backreferences; that is an accepted
  trade for safety and is rarely needed for corpus search. Compile failures (and
  unsupported constructs) surface as the existing `ValidationError`.
- With a safe engine in place, implement the remaining ripgrep-parity flags from
  **#81** — `count_only`, `invert`, `multiline` — on top, within the existing
  budgets.

### Phase 3 — optional cache tier (deferred, unchanged from ADR 0012)

The `cache_elasticache` Redis/Valkey read-through + grep-candidate prefetch
(**#78**) stays **off by default**, the latency knob for hot, high-QPS corpora.
Phase 1 makes it less urgent; it is no longer the *only* lever.

## Why

- **Fix the bottleneck where it is.** The cost is network round-trips, so
  parallelizing the fetch — not a faster scanner — is the highest-leverage move,
  and it needs zero new infrastructure or cost.
- **Safety before features.** A linear-time engine removes a real
  denial-of-service vector on a multi-tenant, untrusted surface; the #81 flags
  ride along for free once the engine is in place.
- **Don't reinvent, don't over-build.** RE2 gives us ripgrep's core guarantee as
  a library; the standing cache and always-on compute remain available as
  deliberate, opt-in accelerators rather than the default.
- **Same seams.** No contract changes — `ObjectStore`/`CatalogStore` are
  untouched; this is service-layer concurrency plus an engine dependency.

## Consequences

- **Amends ADR 0012's "no cache, rely on S3 + budgets."** The stance becomes
  "parallel fetch + a safe engine first; cache is the opt-in tier." ADR 0012's
  two-stage shape and budgets are unchanged.
- **New base dependency (`google-re2`).** A small native wheel. If it is ever
  unavailable on a target, the engine seam can fall back to `re` (with the
  pattern accepted but unsafe) — kept behind one compile point.
- **`truncated: true` will fire more often** for broad greps. That is the honest
  signal; tool docs already say "narrow with `path_glob` / a tighter `pattern`."
- **Concurrency raises peak S3 RPS per call.** Bounded by `PAGE_FETCH_CONCURRENCY`
  (default 16) and the existing file/byte budgets, well within S3 per-prefix
  limits for derived text.

## Alternatives considered

- **Shell out to ripgrep** — rejected as the primary fix (doesn't remove the
  network bottleneck; adds binary/subprocess/temp-file complexity). Its merits
  are captured by RE2 + Phase 1.
- **Pre-warmed / always-on worker with the corpus local** — that is the Fargate
  (#73) + cache (#78) territory; breaks idle-cost and, at "all files,"
  multi-tenant isolation. Kept as opt-in accelerators, not the default.
- **Keep `re` + a complexity guard / timeout** — CPython has no clean per-match
  timeout; mitigation is fragile. Rejected in favor of a linear-time engine.
- **Add Redis now** — still rejected for the default (ADR 0012's idle-cost
  promise); Phase 1 reduces the need. Remains #78, opt-in.
