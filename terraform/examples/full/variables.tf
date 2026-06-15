# Full root — every capability agentic-fs ships today, on. The optional
# *capability* modules (semantic search, Fargate compute, managed Cognito IdP)
# are not yet built; they're documented in main.tf + README and tracked as
# contribution issues, so this root composes everything that exists today and
# leaves a clear slot for the rest.

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
  description = "AFS_AUTH_MODE for the deployed app (\"dev\" or \"oidc\")."
  type        = string
  default     = "oidc"
}

variable "alarm_email" {
  description = "Email subscribed to the alerts topic."
  type        = string
  default     = null
}
