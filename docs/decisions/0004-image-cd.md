# ADR 0004: image CD — CI pushes + rolls the Lambda; Terraform ignores image drift

**Status:** accepted · **Date:** 2026-06-13

## Context

The API runs as a container Lambda whose `image_uri` is a Terraform-managed
attribute. We want continuous delivery (every merge ships the new image) without
Terraform and CI reverting each other, and without a public/mutable tag.

## Decision

- **`image.yml`** (on merge to `master` touching `packages/**` or the
  `Dockerfile`) builds `linux/amd64` and pushes to ECR with the **immutable
  git-SHA tag**, then rolls the function with `aws lambda update-function-code
  --image-uri …:<sha> --publish`.
- The `compute_lambda` module sets `lifecycle { ignore_changes = [image_uri] }`,
  so Terraform sets the *initial* image at creation and never fights CI's rolls.
- A **dedicated least-privilege role** `agentic-fs-ci-image-push` (ECR push on the
  `agentic-fs-api` repo + `lambda:UpdateFunctionCode`/`GetFunction` on the
  function) — *not* the broad apply role — gated to the `sandbox` environment.

## Why

- **Immutable tags + per-commit traceability**: each deploy is a unique SHA tag;
  no moving `latest`, no mutable-tag finding.
- **No two-controllers fight**: `ignore_changes` cleanly splits ownership —
  Terraform owns the function's *config*, CI owns the *running image*.
- **Least privilege**: image delivery doesn't need (and shouldn't have) the
  apply role's PowerUser breadth.
- It also runs the push from GitHub's runners, sidestepping local-network limits
  on large ECR uploads.

## Consequences

- "What image is deployed" lives in the function (last CI roll), not the
  committed Terraform config — read it from `aws lambda get-function`.
- First creation still needs one image in ECR: `image.yml`'s first run provides
  it, then `enable_compute=true` (with that SHA) creates the function; every
  subsequent merge auto-rolls it.
