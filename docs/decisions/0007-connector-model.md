# ADR 0007: connectors are client-side, pluggable, and own their source auth

**Status:** accepted · **Date:** 2026-06-14

## Context

An org's documents live in many sources — a local folder, an S3 prefix, Google
Drive, SharePoint, Confluence — each with a different access model (none, AWS
credentials, per-user OAuth). agentic-fs needs to pull those documents in
*without* coupling the server to any source and *without* the server storing
third-party credentials. We also already have the ingest REST API, `SourceRef`
(connector provenance on a catalog row), and `SyncCheckpoint` (a server-side
cursor) — the connector layer should use them, not reinvent them.

## Decision

Connectors are **clients**, not server plugins. They run *outside* agentic-fs and
**push** to the ingest REST API; the server never reaches out to a source and
never holds a Drive/SharePoint OAuth token.

Three clean responsibilities, mirroring the extraction split (ADR 0006):

- **`Connector`** (`afs_core.contracts.connector`) — *source → items + bytes*.
  Two methods: `discover()` yields `SourceItem`s (a relative `path`, an opaque
  `locator`, optional `size`/`content_type`/`version`); `fetch(item)` returns the
  bytes. It is **synchronous** — most source SDKs (boto3, the Google client,
  filesystem calls) are sync, and the engine adds concurrency by running `fetch`
  in a thread pool. Certified by `afs_core.testing.ConnectorConformance`.
- **`SyncEngine`** (`afs-connector-sdk`) — *source-agnostic orchestration*.
  discover → **skip unchanged** → ingest → optional **prune**. Idempotency is
  decided by comparing the content checksum to the catalog's (`stat` then
  compare), so re-runs are cheap and nothing is re-extracted needlessly; the
  server is the sync state (no client state file). Resumable cursors, when a
  source needs them (e.g. the Drive changes API), persist via `SyncCheckpoint`.
- **`IngestClient` + signers** — *talking to the API*. The doc path is built into
  the request and signed as the **exact final URL the client sends**, which
  sidesteps the SigV4 query-encoding mismatch.

**Two auth seams, deliberately separate:**

1. **Source-side** — *inside each connector*. S3 uses the standard boto3 chain;
   Google Drive will do per-user OAuth; local FS needs nothing. The contract
   never mentions auth, so each source owns its own.
2. **API-side** — a pluggable `RequestSigner` in the SDK: `NoAuth` (dev),
   `SigV4Signer` (the default `AWS_IAM` Function URL), bearer-token (with the
   OAuth resource server).

Connectors are selected by name: builtins **local** and **s3**, plus the
`afs.connectors` entry-point group for third parties. `fs-crawler` is the CLI.

## Why

- **No third-party credentials on the server** — OAuth tokens for Drive/SharePoint
  stay on the client that already has the user's consent; the server's blast
  radius and compliance surface don't grow with every connector.
- **Run anywhere, scale independently** — a connector is a script you run on a
  laptop, a cron, or a Lambda; crawling never competes with serving.
- **Author writes two methods** — everything hard (batching, retries, idempotency,
  pruning, signing) is in the SDK; a new source is `discover` + `fetch` + an
  entry point, certified by the conformance kit. (S3 and Drive both fit.)

## Alternatives considered

- **Server-side pull** (a scheduler in the server with stored OAuth tokens) —
  rejected for v1: it puts third-party credential storage and refresh in the
  server. It can return later as an optional *hosted connectors* deployment that
  reuses this same `Connector` contract.
- **Async connector contract** — rejected: it would force async on every plugin
  author for no gain, since source SDKs are sync and the engine already
  parallelizes `fetch` across threads.

Builtins today: **local FS**, **S3**. Google Drive / SharePoint are
certified-later plugins; the OAuth auth seam is designed for them now. See
[`docs/swap-guides/connectors.md`](../swap-guides/connectors.md).
