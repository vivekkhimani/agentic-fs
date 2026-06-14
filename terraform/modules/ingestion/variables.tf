variable "name_prefix" {
  description = "Prefix for the queue, rule, worker, and role names."
  type        = string
}

variable "image_uri" {
  description = "Worker ECR image URI (e.g. <repo>:worker-<tag>). The afs-server[docling] image."
  type        = string
}

variable "region" {
  description = "AWS region (passed to the worker as AFS_REGION)."
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the data bucket whose object-created events drive extraction."
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
  description = "ARN of the catalog table (indexes scoped as <arn>/index/*)."
  type        = string
}

variable "kms_key_arn" {
  description = "Project CMK ARN — the worker uses it for SSE-KMS reads/writes on S3."
  type        = string
}

variable "permissions_boundary_arn" {
  description = "Permissions boundary attached to the worker exec role (required by the CI apply role's boundary)."
  type        = string
}

variable "extraction_ladder" {
  description = <<-EOT
    AFS_EXTRACTION_LADDER for the worker — light rungs first, then OCR escalation.
    Default matches the slim default worker image (textract = AWS-managed OCR, no
    local ML). If you build the image with --build-arg AFS_EXTRAS=...,docling,
    add "docling" here too so the heavier rung is actually used.
  EOT
  type        = string
  default     = "text_native,pdf,docx,textract"
}

variable "memory_mb" {
  description = <<-EOT
    Worker memory (MB). Sized for the slim default (textract = managed OCR, light
    rasterization). Raise it for a docling/torch build — that's memory-hungry, and
    CPU scales with memory on Lambda (e.g. 3008+ for docling).
  EOT
  type        = number
  default     = 1024
}

variable "timeout_seconds" {
  description = "Worker timeout (seconds). Raise it for a docling build (heavier cold start + per-doc ML inference)."
  type        = number
  default     = 120
}

variable "batch_size" {
  description = "SQS messages per worker invocation. 1 isolates per-document failures cleanly."
  type        = number
  default     = 1
}

variable "max_receive_count" {
  description = "Deliveries before a message is sent to the DLQ."
  type        = number
  default     = 5
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the worker."
  type        = number
  default     = 30
}
