# ADR 0002: pluggable backends via entry points + a settings-selected name

**Status:** accepted · **Date:** 2026-06-13

## Context

agentic-fs is open source and explicitly designed so adopters can run each
stateful layer on the infrastructure they already have (S3 vs R2 vs MinIO;
DynamoDB vs Postgres; Bedrock vs another vector store; Lambda vs Fargate vs a
Cloudflare Worker at the edge). That swap-ability has to be real and low-friction,
not a fork.

## Decision

Every swappable layer is chosen by a **backend name** in settings
(`AFS_<LAYER>_BACKEND`) and resolved by a small registry that checks **builtins
first, then an entry-point group** (`afs.object_stores`, `afs.catalog_stores`,
`afs.search_backends`, `afs.normalizers`, `afs.tools`). Each layer has a
**conformance kit** in `afs_core.testing` that any implementation must pass.

## Why

- **Plug-and-play.** Swapping a backend is `pip install <pkg>` + one env var; the
  server discovers it via entry points and never imports it directly.
- **Provably correct swaps.** "Make the conformance kit green" is an objective bar
  — the same tests certify the in-memory fake, the AWS impl, and a third-party one.
- **S3-compatible is even cheaper.** Because the S3 store speaks plain S3,
  MinIO/R2/Wasabi/B2 need only `AFS_S3_ENDPOINT_URL` — no plugin at all
  (see `docs/swap-guides/object-store.md`).

## Consequences

- Builtins and plugins share one resolution path; an unknown name fails fast with
  the list of available backends.
- Each new contract ships with: the `Protocol`, a conformance kit, a reference
  impl, a Terraform module (where infra-backed), and a one-page swap guide.
