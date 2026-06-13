variable "name_prefix" {
  description = "Prefix applied to the key alias (`alias/<name_prefix>-data`)."
  type        = string
}

variable "deletion_window_in_days" {
  description = "Waiting period (days) before the CMK is deleted after a destroy. 7–30."
  type        = number
  default     = 30

  validation {
    condition     = var.deletion_window_in_days >= 7 && var.deletion_window_in_days <= 30
    error_message = "deletion_window_in_days must be between 7 and 30."
  }
}
