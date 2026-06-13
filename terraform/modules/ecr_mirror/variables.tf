variable "name_prefix" {
  description = "Prefix for the repository name (`<name_prefix>-api`)."
  type        = string
}

variable "untagged_expiry_days" {
  description = "Expire untagged images after this many days to keep the repo small."
  type        = number
  default     = 14
}
