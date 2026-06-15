# Hardened root — the quickstart footprint with defense-in-depth turned on, using
# only modules implemented today. Headline hardening that needs not-yet-built
# modules (GuardDuty malware scan, access-log bucket, private network, per-request
# session scoping) is documented in main.tf + README and tracked as contribution
# issues.

variable "aws_region" {
  description = "AWS region to deploy agentic-fs into."
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID — the allowed-account guard + global-uniqueness suffix."
  type        = string
}

variable "name_prefix" {
  description = "Prefix applied to every resource name (`<name_prefix>-<component>`)."
  type        = string
  default     = "agentic-fs"
}

variable "env" {
  description = "Environment label applied as the `Env` tag on every resource."
  type        = string
  default     = "prod"
}

variable "image_tag" {
  description = "Tag of the API/worker image in ECR used to CREATE the Lambdas."
  type        = string
  default     = "b0bd416c42e9"
}

variable "auth_mode" {
  description = "AFS_AUTH_MODE — hardened defaults to the OIDC resource server (set the AFS_OIDC_* env on the function or via extra_env)."
  type        = string
  default     = "oidc"
}

variable "alarm_email" {
  description = "Email subscribed to the alerts topic (hardened deployments should set this)."
  type        = string
  default     = null
}

variable "kms_deletion_window_in_days" {
  description = "CMK deletion waiting period — max (30) for hardened."
  type        = number
  default     = 30
}
