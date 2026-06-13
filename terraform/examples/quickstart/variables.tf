# Quickstart variable budget: `aws_region` is the only required input; every
# other knob is defaulted so a fresh account reaches a working endpoint with one
# `terraform apply`. Keep the surfaced set <= 10 variables (plan §11.3).

variable "aws_region" {
  description = "AWS region to deploy agentic-fs into."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID — used as the allowed-account guard and the global-uniqueness suffix on bucket/table names."
  type        = string
  default     = "002988089284"
}

variable "name_prefix" {
  description = "Prefix applied to every resource name (`<name_prefix>-<component>`)."
  type        = string
  default     = "agentic-fs"
}

variable "env" {
  description = "Environment label applied as the `Env` tag on every resource."
  type        = string
  default     = "sandbox"
}
