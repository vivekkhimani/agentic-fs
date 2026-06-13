# `storage` — data bucket

The single canonical S3 store (plan §3). Channel-first keys: `tenants/` (raw
canonical documents), `derived/` (extracted text + manifests + tree artifacts),
`scratch/` (agent scratch, TTL'd). S3 is the source of truth; everything else is
healable from it.

## Resources

- `aws_s3_bucket.data` — `<name_prefix>-data-<account_id>`.
- Ownership `BucketOwnerEnforced` (ACLs disabled) + full public-access block.
- Versioning enabled (raw is canonical).
- SSE-KMS with the project CMK, bucket keys enabled.
- EventBridge notifications enabled (one rule will feed the extract pipeline).
- Lifecycle: `abort-multipart` (3d), `scratch-ttl` (expire `scratch/` after
  `scratch_ttl_days` + drop noncurrent fast), `derived-noncurrent` (7d),
  `tenants-noncurrent` (`tenants_noncurrent_days`), optional
  `tenants-intelligent-tiering`.
- Bucket policy: TLS-only deny, deny PUT without `SSE-KMS`, and (when
  `quarantine_exempt_role_arns` is set) deny reads of GuardDuty-flagged objects
  to all but the scanner/extractor.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | string | — | Bucket name prefix. |
| `account_id` | string | — | Global-uniqueness suffix. |
| `kms_key_arn` | string | — | Project CMK for SSE-KMS. |
| `scratch_ttl_days` | number | `7` | TTL for `scratch/`. |
| `tenants_noncurrent_days` | number | `30` | Noncurrent retention for `tenants/`. |
| `enable_intelligent_tiering` | bool | `true` | Tier `tenants/` to Intelligent-Tiering. |
| `quarantine_exempt_role_arns` | list(string) | `[]` | Roles exempt from the malware-quarantine deny. |

## Outputs

| Name | Description |
|---|---|
| `bucket_name` | Data bucket name. |
| `bucket_arn` | Data bucket ARN. |
| `bucket_regional_domain_name` | Regional domain name. |

## Deferred

`enable_access_logs` (optional S3 server-access-logging bucket, plan §3.3) — not
yet implemented; CloudTrail S3 data events (`observability` module) are the
preferred audit story. Added here as a gated logs bucket when needed.
