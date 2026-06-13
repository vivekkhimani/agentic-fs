# ADR 0001: sync boto3 wrapped in `asyncio.to_thread`, not aioboto3

**Status:** accepted · **Date:** 2026-06-13

## Context

The store contracts are async. AWS access can be async (`aioboto3`/`aiobotocore`)
or sync boto3 offloaded to a thread.

## Decision

Implement the AWS-backed stores with **sync boto3**, wrapping each call in
`asyncio.to_thread`.

## Why

- **Testability.** `moto` (the standard AWS mock) patches botocore and works
  out-of-the-box with sync boto3 in-process — so the conformance kit runs against
  the real store with zero infrastructure. `aiobotocore` uses a different HTTP
  stack that moto's default mock doesn't intercept, which would force a
  moto-server container just to unit-test a store.
- **Fit for the serving model.** The default compute is request-scoped Lambda
  with low per-container concurrency; a thread hop per S3/DynamoDB call is
  negligible and never the bottleneck.
- **Simplicity & ecosystem.** boto3 is the most complete, best-documented AWS
  SDK; no extra async-AWS dependency to track.

## Consequences

- A small thread-pool hop per AWS call (fine for our concurrency profile).
- If a future high-fan-out workload needs true async AWS I/O, a store can switch
  to `aioboto3` behind the same `ObjectStore`/`CatalogStore` contract without
  touching callers — revisit then.
