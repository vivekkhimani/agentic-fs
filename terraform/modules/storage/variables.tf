variable "name_prefix" {
  description = "Prefix applied to bucket names (`<name_prefix>-data-<account_id>`)."
  type        = string
}

variable "account_id" {
  description = "AWS account ID — the global-uniqueness suffix on the bucket name."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the project CMK used for SSE-KMS on the data bucket."
  type        = string
}

variable "scratch_ttl_days" {
  description = "Days after which objects under scratch/ expire (agent scratch space is ephemeral)."
  type        = number
  default     = 7
}

variable "tenants_noncurrent_days" {
  description = "Days to retain noncurrent versions of canonical documents under tenants/ before expiry."
  type        = number
  default     = 30
}

variable "enable_intelligent_tiering" {
  description = "Transition canonical documents under tenants/ to S3 Intelligent-Tiering. Disable for tiny corpora where the per-object monitoring fee isn't worth it."
  type        = bool
  default     = true
}

variable "quarantine_exempt_role_arns" {
  description = <<-EOT
    Role ARNs exempt from the malware-quarantine deny (the scanner + extractor).
    When non-empty, the bucket policy denies s3:GetObject on objects tagged with
    a GuardDuty THREATS_FOUND scan result to every principal EXCEPT these roles.
    Empty (default) = no quarantine statement (GuardDuty scanning not enabled).
  EOT
  type        = list(string)
  default     = []
}
