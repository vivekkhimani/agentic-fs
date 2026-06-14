# `observability` — high-signal alarms over the deployed footprint

**Status: implemented.** Default footprint.

One **SNS alerts topic** plus a small, deliberately **high-signal** set of
CloudWatch alarms — each means "a human should look", not "fyi". Every alarm is
**component-gated**: it's created only when you pass that component's name, so the
same module fits the quickstart, a compute-only root, or a full footprint.

## Alarms

| Alarm | Metric | Fires when | Why it's high-signal |
|---|---|---|---|
| `dlq-not-empty` | SQS `ApproximateNumberOfMessagesVisible` (DLQ) | ≥ 1 message | A doc failed extraction after **all** retries — needs a human + redrive |
| `extract-backlog-stuck` | SQS `ApproximateAgeOfOldestMessage` | oldest > `extract_backlog_age_seconds` (900s) | Worker is failing/behind — the catalog is going stale |
| `api-errors` | Lambda `Errors` (API) | ≥ `lambda_error_threshold` | The MCP/REST surface is degraded |
| `api-throttles` | Lambda `Throttles` (API) | ≥ 1 | Requests failing on concurrency limits |
| `worker-errors` | Lambda `Errors` (worker) | ≥ `lambda_error_threshold` | Extraction breaking; docs stuck `catalog_only` |
| `reconciler-errors` | Lambda `Errors` (reconciler) | ≥ `lambda_error_threshold` | Drift goes unhealed |
| `catalog-throttles` | DynamoDB `ThrottledRequests` | > 0 for `dynamodb_throttle_evaluation_periods` (3×5m) | list/stat/ingest failing on capacity |

Alarms send on **both** fire and clear (`alarm_actions` + `ok_actions`), so a
recovery is as visible as a break. `treat_missing_data = notBreaching` (no data =
healthy) keeps an idle, near-$0 deployment quiet.

## Inputs

`name_prefix`; optional `alarm_email` (an email subscription — or wire your own
subscriber to the topic ARN); the component names to watch (`api_function_name`,
`worker_function_name`, `reconciler_function_name`, `extract_queue_name`,
`dlq_name`, `catalog_table_name` — all nullable); and thresholds
(`lambda_error_threshold`, `lambda_error_period_seconds`,
`extract_backlog_age_seconds`, `dynamodb_throttle_evaluation_periods`).

## Outputs

`alerts_topic_arn` (subscribe Slack/PagerDuty/chatbot here) and `alarm_names`
(the alarms actually created for this footprint).

## Notes

The CI apply role permits CloudWatch + SNS within the project's region/scope via
its allow-ceiling + deny-guardrails, so no `ci-roles` change is needed. Explicit
log-group retention and an optional dashboard / AWS Budgets are future toggles.

**SNS encryption** is a deliberate, scoped exception (`#trivy:ignore:AWS-0095`):
the topic carries alarm *metadata*, not tenant data; and CMK-encrypting it against
the root-only project CMK would break CloudWatch→SNS delivery (the key doesn't
grant the CloudWatch service principal). CMK encryption with an explicit
CloudWatch key grant is a future hardening toggle, best validated live.

Conventions: HashiCorp style-guide layout (`terraform.tf`/`main.tf`/`variables.tf`/`outputs.tf`),
typed + documented variables, `<name_prefix>-<component>` naming, no
backend/provider block (composed from the example roots).
