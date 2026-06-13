# ADR 0003: one container image for Lambda + Fargate, via the Web Adapter

**Status:** accepted · **Date:** 2026-06-13

## Context

The default serving compute is Lambda (Function URL, streaming), but the same
service must also run on Fargate/ECS (always-on, OCR-at-scale) and locally — and
the image is published for adopters, so it has to be small and secure.

## Decision

A single image (`Dockerfile`) built as:

- **Base:** `python:3.12-slim-bookworm` (pinned). Not distroless — we want a
  shell for the healthcheck and debuggability, and the size delta is small.
- **Multi-stage + uv:** a builder stage resolves and installs from the committed
  `uv.lock` (cache-mounted `~/.cache/uv`; deps layer separated from source so it
  caches across code edits), then installs the workspace packages as built wheels
  (`--no-editable`). The runtime stage copies only the `.venv` — no source, no uv,
  no build tools.
- **AWS Lambda Web Adapter** copied into `/opt/extensions`: it forwards Lambda
  Function URL invocations (including response streaming) to the local uvicorn
  server, so **the same image runs uvicorn on Lambda, Fargate, and a laptop**. On
  non-Lambda it is inert.
- **Security:** non-root user (uid 10001), no secrets in any layer (config is all
  runtime env), `.dockerignore` keeps `.git`/`.env`/infra/docs out of context, a
  `HEALTHCHECK` hits `/v1/healthz`.

## Why

- **One image, three targets** removes the "Lambda runtime interface vs a normal
  web server" fork — uvicorn is the single entrypoint everywhere, so local dev is
  faithful to production.
- **uv + cache mounts + lockfile** give fast, reproducible builds; `--no-editable`
  keeps the runtime image minimal (~190 MB) and free of source/build tooling.
- **Slim + non-root + no-secrets** is the baseline the container-security and
  docker-patterns skills call for.

## Consequences

- The Web Adapter version is pinned and updated deliberately.
- Verified: the image builds, serves `/v1/healthz`, and runs as non-root.
- `compute_lambda`/`compute_fargate` Terraform modules consume this image from
  ECR; the Cloudflare Worker edge option is a *different* deployment that calls
  this image's REST API (`docs/swap-guides/compute.md`).
