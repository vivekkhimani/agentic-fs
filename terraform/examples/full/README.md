# Example: full (doc stub)

**Status: documented, not yet buildable** — composes modules that are still
scaffolds. This file reserves the shape; the `.tf` lands with the modules.

Every optional capability enabled — the "show me everything" reference:

- `enable_search = true` — Bedrock Knowledge Base on S3 Vectors
- `enable_fargate = true` — always-on API behind an ALB (+ `network`)
- `enable_cognito = true` — managed OAuth IdP
- `enable_guardduty_scan`, `enable_cloudtrail_data_events`, `enable_dashboard`
- `monthly_budget_usd` set → AWS Budgets alert

Until then, use [`../quickstart`](../quickstart). See
`docs/agentic-fs-oss-plan.md` §11 for the module set.
