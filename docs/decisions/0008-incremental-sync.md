# ADR 0008: incremental sync — version-skip + delta cursors (engine-owned)

**Status:** accepted · **Date:** 2026-06-14

## Context

The v1 connector sync ([ADR 0007](0007-connector-model.md)) is correct but does a
**full scan every run**: it enumerates the whole source and **fetches every file**
to checksum it, skipping only the re-ingest. That's fine for a local folder and
ruinous for a nightly sync of a 100k-file Google Drive or SharePoint — a full
download plus an API call per file, every night.

A scan has two costs: **(a)** enumerating the source and **(b)** fetching each
file's bytes. Incremental sync must cut both, without pushing complexity into
every connector.

## Decision

Two complementary layers, both **engine-owned**; connectors stay thin.

- **L1 — skip the *fetch*** (cuts cost b, every connector). On ingest the engine
  records the source change-token in `SourceRef.version` (etag / mtime / revision)
  on the catalog row. Next run it `stat`s the entry and, if the discovered
  `SourceItem.version` matches the stored one, **skips the fetch entirely** and
  moves on. Content checksum stays the authority *when* we do fetch, so a
  same-version-different-content edge (rare) self-heals on the next changed scan.
- **L2 — skip the *enumeration*** (cuts costs a + b, delta-capable sources). A
  connector may *optionally* implement `IncrementalConnector.discover_changes(cursor)`
  over the source's native delta feed (Drive `changes.list`, Graph `delta`). The
  engine passes the last cursor, processes only the returned `ChangeSet` (changed
  items + deleted paths), and persists the new cursor. First run (`cursor=None`)
  returns everything plus a starting cursor.

**Where each piece lives** — the question that matters:

| Piece | Home |
|---|---|
| Cursor + per-file version storage | **server** — `SyncCheckpoint` (already modeled) via a new `GET/PUT /v1/connectors/{id}/checkpoint`; `SourceRef.version` (already on the row) set by ingest |
| The sync loop (full vs. delta, version-skip, persist cursor, apply deletes) | **engine** (`afs-connector-sdk`) |
| "What changed since cursor X" | **connector** — the only source-specific part |

So a non-delta connector (Local FS, S3) gets L1 for free; a delta-capable one
(Drive, SharePoint) adds one method for L2. Checkpoints live **server-side** so
the corpus is self-describing and any runner of the connector resumes the same
cursor.

## Why

- **Scales to massive sources** — a nightly Drive sync touches only what changed,
  not the whole tree.
- **Connectors stay thin** — L1 is automatic; L2 is one optional method. No
  connector reimplements checkpointing, version comparison, or delete handling.
- **Reuses what's modeled** — `SyncCheckpoint`, `SourceRef.version`, and the
  catalog's `get/put_checkpoint` already exist; this slice exposes them, it
  doesn't invent state.

## Alternatives considered

- **Client-side checkpoint file** — rejected: the cursor would be tied to one
  machine; server-side keeps the corpus self-describing and lets any runner
  resume.
- **Trust mtime/etag alone (drop the checksum)** — rejected: version-skip is an
  optimization layered *over* the content checksum, which stays authoritative
  whenever bytes are actually fetched.

Builtins (Local FS, S3) ship L1 now; the `IncrementalConnector` contract + cursor
plumbing land here and are first consumed by the Google Drive connector
([connectors swap guide](../swap-guides/connectors.md)).
