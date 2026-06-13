# Example: hardened (doc stub)

**Status: documented, not yet buildable** — composes modules that are still
scaffolds. This file reserves the shape; the `.tf` lands with the modules.

The `quickstart` footprint with defense-in-depth turned on:

- `enable_session_policy_scoping = true` — per-request STS scoping (Layer 2)
- `enable_guardduty_scan = true` — S3 malware scanning + quarantine gate
- `enable_cloudtrail_data_events = true` — object-level audit trail
- `enable_access_logs = true`
- private-subnet + NAT network variant when `enable_fargate = true`

Until then, use [`../quickstart`](../quickstart). See
`docs/agentic-fs-oss-plan.md` §4 and §11 for the hardening model.
