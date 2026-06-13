variable "name_prefix" {
  description = "Prefix for the function, role, and log group names."
  type        = string
}

variable "image_uri" {
  description = "ECR image URI the Lambda runs (e.g. <repo>:<tag>)."
  type        = string
}

variable "region" {
  description = "AWS region (passed to the app as AFS_REGION)."
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the data bucket the API reads."
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the data bucket (for IAM scoping)."
  type        = string
}

variable "catalog_table_name" {
  description = "Name of the DynamoDB catalog table."
  type        = string
}

variable "catalog_table_arn" {
  description = "ARN of the catalog table (for IAM scoping; indexes are scoped as <arn>/index/*)."
  type        = string
}

variable "kms_key_arn" {
  description = "Project CMK ARN — the exec role gets kms:Decrypt on it for SSE-KMS reads."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "Permissions boundary attached to the Lambda exec role (required by the CI apply role's boundary)."
  type        = string
}

variable "function_url_auth_type" {
  description = <<-EOT
    Function URL authorization: "AWS_IAM" (default — only IAM-signed callers,
    safe while app-layer OAuth doesn't exist yet) or "NONE" (public; only set
    this once the OAuth resource server terminates auth in-app).
  EOT
  type        = string
  default     = "AWS_IAM"

  validation {
    condition     = contains(["AWS_IAM", "NONE"], var.function_url_auth_type)
    error_message = "function_url_auth_type must be AWS_IAM or NONE."
  }
}

variable "auth_mode" {
  description = "AFS_AUTH_MODE for the app (\"dev\" until the OAuth resource server lands)."
  type        = string
  default     = "dev"
}

variable "memory_mb" {
  description = "Lambda memory (MB). Container cold start + the ASGI stack wants headroom."
  type        = number
  default     = 1024
}

variable "timeout_seconds" {
  description = "Lambda timeout (seconds)."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the function."
  type        = number
  default     = 30
}

variable "extra_env" {
  description = "Additional AFS_* environment variables to set on the function."
  type        = map(string)
  default     = {}
}
