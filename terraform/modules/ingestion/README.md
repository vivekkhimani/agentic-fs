# `ingestion` — async extraction pipeline

**Status: implemented (default footprint).** Async extraction per
[ADR 0009](../../../docs/decisions/0009-async-extraction-pipeline.md).

S3 object-created events on the data bucket (already emitted to EventBridge by the
`storage` module) under `tenants/` → **SQS** (+ DLQ) → the **docling extractor
worker Lambda** (the `afs-server[docling]` image) via an event-source mapping. The
worker reads the original, runs the pipeline, and writes the derived pages + the
catalog row's extraction state.

Inputs: `name_prefix`, `image_uri` (the `worker-<tag>` image), `region`, the data
bucket + catalog table name/ARN, `kms_key_arn`, `permissions_boundary_arn`, and
tunables (`memory_mb`, `timeout_seconds`, `batch_size`, `max_receive_count`,
`extraction_ladder`, `log_retention_days`). Outputs: queue/DLQ ARNs + the worker
function name/ARN.

The worker exec role is least-privilege (read originals, write derived, catalog
R/W, CMK use, consume the queue) and carries the project permissions boundary. No
apply-role change is needed — PowerUser covers SQS/EventBridge/Lambda, and the
`agentic-fs-*`-prefixed exec role is within the role's scoped IAM writes.

Conventions: HashiCorp style-guide layout, typed + documented variables,
`<name_prefix>-<component>` naming, no backend/provider block (composed from the
example roots).
