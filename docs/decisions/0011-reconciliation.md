# ADR 0011: catalog↔S3 reconciliation

**Status:** accepted · **Date:** 2026-06-14

## Context

S3 is canonical; the catalog (DynamoDB) is a **derived, healable projection** of
it. The event path (S3 → EventBridge → SQS → worker, [ADR 0009](0009-async-extraction-pipeline.md))
keeps the catalog in sync, but events get missed, the worker can fail past the
DLQ, and objects can be dropped into or deleted from S3 **directly** (`aws s3
sync`, a bulk load, a manual delete) — bypassing the API entirely. Without a
backstop the projection drifts: objects with no row (invisible), rows with no
object (dangling), or stale rows after an overwrite. The promise is "rebuildable
from S3," so we need a periodic sweep that heals drift. Reconciliation is a
classically tricky problem (races, idempotency, the delete/re-add round-trip), so
the decision and its **state table** are recorded here to refer back to.

## Decision

A scheduled **reconciler** (EventBridge rate → Lambda, `afs_server.reconcile`)
diffs S3 against the catalog per `(tenant, namespace)` and heals both directions.
It only **detects** drift — re-extraction is delegated to the worker via the
existing extract queue; the reconciler just enqueues and tombstones. S3 is the
source of truth.

### The state table (the canonical reference)

For each path, given the S3 object and the catalog row:

| S3 object | catalog row | Action |
|---|---|---|
| present | **no row** | enqueue → worker extracts (new row) |
| present | **tombstoned** (`deleted`) | enqueue → **revives** the file (deleted-then-re-added) |
| present | live, **etag ≠** object | enqueue → re-extract (object changed) |
| present | live, etag matches | **in sync** — no-op |
| **absent** | live | **soft-delete** (tombstone), past a grace window |
| absent | tombstoned | already healed — no-op |

- **Soft-delete, never hard.** Tombstoning sets `deleted_at` (hidden from
  get/list) but keeps the row, its `entry_id`, and history. This is what makes
  the **delete → re-add round-trip** clean: a returning object is *revived*
  (row goes live again on re-extract), not recreated from nothing. A hard delete
  would throw the row away and lose that reversibility — so we don't.
- **Grace period** (`reconcile_grace_seconds`, default 900s): never tombstone a
  row whose object we can't see if the row was written within the window — guards
  against racing a fresh write or a stale list snapshot.
- **Delegates work:** drift → an SQS message in the worker's "Object Created"
  shape; the worker's idempotent `extract_object` does the extraction. The
  reconciler needs no extraction deps (no `GetObject`, no CMK — just
  `s3:ListBucket`, catalog scan + tombstone, `sqs:SendMessage`).
- **Scope:** only `tenants/` originals (derived/scratch skipped via `parse_key`).
  Catalog-only namespaces (all objects gone, only orphans left) are found by
  enumerating namespaces from the catalog, not just from S3.

## Why

- **Heals every drift source** the event path can't guarantee — missed events,
  DLQ-exhausted failures, direct S3 mutations — so the catalog converges to S3.
- **Idempotent + safe:** in-sync rows are skipped; enqueues hit the idempotent
  worker; re-running changes nothing. The grace period + soft-delete mean the
  sweep can't destroy data or fight a concurrent write.
- **Reversible deletes** make the re-add case correct by construction (see table).
- **Separation of concerns:** detection (reconciler) vs extraction (worker) keeps
  the reconciler light and reuses the proven, idempotent extraction path.

## Consequences

- **Revival currently mints a new `entry_id`** (the worker treats a tombstone as
  absent and creates a fresh row), so the old `entry_id`'s `derived/` pages are
  orphaned in S3 — harmless, bounded cruft, and citations by `entry_id` change on
  revival. A follow-up could make revival *reuse* the tombstoned `entry_id`
  (stable citations, no orphans) by reviving the existing row instead.
- **Full sweep per run** (all namespaces) — fine at current scale; a large corpus
  would shard by namespace/time across scheduled runs. The sweep cost is S3 LIST +
  a catalog scan per run.
- **Deploy:** the reconciler runs the **worker image** with the reconcile handler,
  so CD must roll it (image.yml) and the CI roll role must include its ARN
  (`ci-roles`, a separate root → manual apply) — same pattern as the worker.
- **Eventual, not instant:** drift heals on the next sweep (default hourly), not
  immediately. The event path remains the fast path; the reconciler is the floor.

## Portability (bring-your-own catalog/storage)

Reconciliation travels with the swappable backends — you never write your own. The
`reconcile()` algorithm is written **only against the `ObjectStore` + `CatalogStore`
contracts** (`objects.list`, `list_entries(include_deleted=True)`, `list_tenants`/
`list_namespaces`, soft `delete_entry`) — no S3/DynamoDB specifics. So:

- **Any conforming backend gets it for free.** Every method *and semantic* the
  reconciler needs is in the Protocols and certified by `CatalogStoreConformance` /
  `ObjectStoreConformance` — including soft-delete/tombstone, the **revival**
  round-trip (a put over a tombstone clears `deleted_at`), `include_deleted`
  listing, prefix pagination, and tenants/namespaces. **Pass conformance ⇒
  reconciliation works.** A BYO catalog that hard-deletes instead of tombstoning
  fails conformance.
- **The shipped runner is backend-agnostic too.** The reconciler Lambda builds its
  stores through the same pluggable registry (`get_catalog_store` /
  `get_object_store`), so a BYO backend works in the provided runner — just set
  `AFS_CATALOG_BACKEND` / `AFS_OBJECT_STORE_BACKEND`.
- **Only the *runner* is environment-specific.** The schedule + handler + the
  `enqueue` callable are one AWS deployment of the portable core. Non-AWS
  deployments call `reconcile(catalog, objects, enqueue)` from their own scheduler
  (cron/k8s) with their own enqueue — no reconciler rewrite. There is deliberately
  **no pluggable "Reconciler" interface**: the swappable surface is the stores, and
  reconciliation is a capability they provide.

## Alternatives considered

- **Hard-delete orphaned rows.** Simpler, but loses reversibility and history, and
  makes a re-added file a brand-new document (new `entry_id`, orphaned derived).
  Rejected — soft-delete is strictly safer and round-trips cleanly.
- **No grace period.** Simpler, but risks tombstoning a row mid-write or against a
  stale list snapshot. Rejected — the window is cheap insurance.
- **Reconciler does extraction inline.** Fewer moving parts, but couples the sweep
  to the heavy extraction deps and duplicates the worker. Rejected — enqueue to
  the worker instead.
- **Event-only (no reconciler).** Relies on EventBridge/SQS never dropping and no
  direct S3 mutations — not true in practice; drift would accumulate silently.
