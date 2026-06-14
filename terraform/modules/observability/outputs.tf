output "alerts_topic_arn" {
  description = "SNS topic every alarm publishes to (fire + clear). Wire your own subscribers (Slack/PagerDuty/chatbot) here."
  value       = aws_sns_topic.alerts.arn
}

output "alarm_names" {
  description = "Names of the alarms actually created for this footprint."
  value = concat(
    aws_cloudwatch_metric_alarm.dlq_not_empty[*].alarm_name,
    aws_cloudwatch_metric_alarm.extract_backlog_stuck[*].alarm_name,
    aws_cloudwatch_metric_alarm.api_errors[*].alarm_name,
    aws_cloudwatch_metric_alarm.api_throttles[*].alarm_name,
    aws_cloudwatch_metric_alarm.worker_errors[*].alarm_name,
    aws_cloudwatch_metric_alarm.reconciler_errors[*].alarm_name,
    aws_cloudwatch_metric_alarm.catalog_throttles[*].alarm_name,
  )
}
