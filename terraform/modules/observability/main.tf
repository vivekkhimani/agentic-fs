# ---------------------------------------------------------------------------
# observability — high-signal CloudWatch alarms over the deployed footprint,
# fanned out through one SNS topic.
#
# Every alarm is component-gated (created only when its target name is passed),
# so the same module fits the quickstart, a compute-only, or a full footprint.
# The set is deliberately small and actionable — each alarm means "a human
# should look", not "fyi": poison messages, a stuck backlog, function errors /
# throttles, and sustained catalog throttling.
# ---------------------------------------------------------------------------

# The alerts topic carries operational alarm metadata (names, states, reasons,
# resource names) — never tenant/document data, which is CMK-encrypted at its
# source. SSE here is deliberately deferred: the project CMK is root-only by
# design (authority delegated via IAM), so encrypting this topic with it would
# silently break CloudWatch -> SNS delivery (the cloudwatch service principal
# isn't granted on the key), and the AWS-managed SNS key has the same problem.
# CMK encryption with an explicit CloudWatch key grant is a future hardening
# toggle (best validated against the live account). Scoped exception, parallel to
# the remote-state bucket's SSE-S3 exception in global/bootstrap.
#trivy:ignore:AWS-0095
resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alarm_email == null ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  # Both fire and clear go to the topic, so a recovery is as visible as a break.
  actions = [aws_sns_topic.alerts.arn]
}

# --- SQS: poison messages + stuck backlog (the loudest ingestion signals) -----

resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  count = var.dlq_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-dlq-not-empty"
  alarm_description   = "Messages are in the extract DLQ — extraction failed after all retries. Inspect, fix, then redrive."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}

resource "aws_cloudwatch_metric_alarm" "extract_backlog_stuck" {
  count = var.extract_queue_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-extract-backlog-stuck"
  alarm_description   = "Oldest extract message exceeds the age budget — the worker is failing or far behind, so the catalog is going stale."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = var.extract_queue_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.extract_backlog_age_seconds
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}

# --- Lambda: errors + throttles per deployed function -------------------------

resource "aws_cloudwatch_metric_alarm" "api_errors" {
  count = var.api_function_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-api-errors"
  alarm_description   = "The API Lambda is erroring — the MCP/REST surface is degraded."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.api_function_name }
  statistic           = "Sum"
  period              = var.lambda_error_period_seconds
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.lambda_error_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}

resource "aws_cloudwatch_metric_alarm" "api_throttles" {
  count = var.api_function_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-api-throttles"
  alarm_description   = "The API Lambda is being throttled — requests are failing on concurrency limits; raise reserved/limit."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = var.api_function_name }
  statistic           = "Sum"
  period              = var.lambda_error_period_seconds
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}

resource "aws_cloudwatch_metric_alarm" "worker_errors" {
  count = var.worker_function_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-worker-errors"
  alarm_description   = "The extractor worker is erroring — failed messages will land in the DLQ; documents stay catalog_only."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.worker_function_name }
  statistic           = "Sum"
  period              = var.lambda_error_period_seconds
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.lambda_error_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}

resource "aws_cloudwatch_metric_alarm" "reconciler_errors" {
  count = var.reconciler_function_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-reconciler-errors"
  alarm_description   = "The reconciler is erroring — catalog/S3 drift will go unhealed (orphans not tombstoned, re-adds not re-extracted)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.reconciler_function_name }
  statistic           = "Sum"
  period              = var.lambda_error_period_seconds
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.lambda_error_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}

# --- DynamoDB: sustained catalog throttling -----------------------------------

resource "aws_cloudwatch_metric_alarm" "catalog_throttles" {
  count = var.catalog_table_name == null ? 0 : 1

  alarm_name          = "${var.name_prefix}-catalog-throttles"
  alarm_description   = "The catalog table is throttling requests over several periods — list/stat/ingest are failing; investigate hot keys or capacity."
  namespace           = "AWS/DynamoDB"
  metric_name         = "ThrottledRequests"
  dimensions          = { TableName = var.catalog_table_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = var.dynamodb_throttle_evaluation_periods
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.actions
  ok_actions          = local.actions
}
