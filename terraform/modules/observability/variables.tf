variable "name_prefix" {
  description = "Prefix for the SNS topic and alarm names (`<name_prefix>-<component>-<condition>`)."
  type        = string
}

variable "alarm_email" {
  description = "Optional email subscribed to the alerts topic (confirm via the AWS email). When null, the topic is created with no subscription — wire your own (Slack/PagerDuty/chatbot) to its ARN."
  type        = string
  default     = null
}

# --- the deployed components to watch (all optional: an alarm is created only
# --- for the components actually passed in, so partial footprints stay clean) ---

variable "api_function_name" {
  description = "API Lambda function name (errors + throttles). Null to skip."
  type        = string
  default     = null
}

variable "worker_function_name" {
  description = "Extractor worker Lambda function name (errors). Null to skip."
  type        = string
  default     = null
}

variable "reconciler_function_name" {
  description = "Reconciler Lambda function name (errors). Null to skip."
  type        = string
  default     = null
}

variable "extract_queue_name" {
  description = "Extract SQS queue name (oldest-message age = backlog stuck). Null to skip."
  type        = string
  default     = null
}

variable "dlq_name" {
  description = "Dead-letter queue name (any message = poison after retries). Null to skip."
  type        = string
  default     = null
}

variable "catalog_table_name" {
  description = "DynamoDB catalog table name (throttled requests). Null to skip."
  type        = string
  default     = null
}

# --- thresholds (high-signal defaults; raise on a busy deployment) -------------

variable "lambda_error_threshold" {
  description = "Fire when a function records at least this many Errors in a period. 1 = page on any error (right for low-traffic); raise for chatty prod."
  type        = number
  default     = 1
}

variable "lambda_error_period_seconds" {
  description = "Period over which Lambda Errors/Throttles are summed."
  type        = number
  default     = 300
}

variable "extract_backlog_age_seconds" {
  description = "Fire when the oldest extract message is older than this — the worker is stuck or far behind. Defaults to the reconcile grace window."
  type        = number
  default     = 900
}

variable "dynamodb_throttle_evaluation_periods" {
  description = "Consecutive 5-min periods of catalog throttling before firing (on-demand tables throttle briefly during scale-up; require it to persist)."
  type        = number
  default     = 3
}
