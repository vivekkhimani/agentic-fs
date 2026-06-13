variable "name_prefix" {
  description = "Prefix applied to the table name (`<name_prefix>-catalog`)."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of the project CMK used for SSE-KMS on the table."
  type        = string
}

variable "deletion_protection_enabled" {
  description = "Block accidental table deletion. The catalog is a derived index (rebuildable from S3), but its loss forces a full reconciliation sweep — protect it by default."
  type        = bool
  default     = true
}

variable "point_in_time_recovery_enabled" {
  description = "Enable continuous backups (PITR) for restore-to-timestamp."
  type        = bool
  default     = true
}
