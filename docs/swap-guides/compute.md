# Swap guide: serving compute

The same container image (`Dockerfile`, [ADR 0003](../decisions/0003-container-image.md))
runs the agentic-fs API on multiple compute targets. Pick the one you already
operate — the application code is identical.

| Target | How | When |
|---|---|---|
| **Lambda + Function URL** (default) | the image's AWS Lambda Web Adapter forwards invocations (incl. streaming) to uvicorn; deploy via the `compute_lambda` Terraform module | near-$0 idle, bursty traffic, no servers to run |
| **Fargate / ECS** | run the *same* image behind an ALB; deploy via `compute_fargate` (+ `network`) | always-on, no cold starts, heavy OCR |
| **Local** | `make dev` (MinIO + DynamoDB Local + the api) | development |

These three are the same process (uvicorn) — no code change, just where it runs.

## Edge option: Cloudflare Worker (terminate MCP/OAuth at the edge)

The Worker is **not** another place the app runs — it's a thin edge layer that
terminates MCP + OAuth and calls the REST API (which stays the enforcement
boundary). It authorizes nothing authoritatively; it forwards the caller's bearer
token to the data plane.

- Lives in `workers/mcp-edge/` (TypeScript), deployed with **Wrangler**, not
  Terraform ([planned] — the tool surface is generated from the OpenAPI schema so
  it can't drift from the server).
- Use it when you want MCP served from Cloudflare's edge in front of an
  AWS-hosted (or any) agentic-fs REST deployment.

## Writing another compute target

Anything that can run a container or proxy to the REST API works. The contract the
rest of the system relies on is **the REST surface** (`/v1/...`, OpenAPI-described)
— not the runtime. So a new target is either:

1. run the published image (any container platform), or
2. put an edge/proxy in front of the REST API (like the Worker).

No application code changes for either.
