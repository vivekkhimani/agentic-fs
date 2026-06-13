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

variable "enable_compute" {
  description = "Deploy the API Lambda + Function URL. Requires the image to be pushed to ECR first (see README)."
  type        = bool
  default     = true
}

variable "image_tag" {
  description = <<-EOT
    Tag of the API image in ECR used to CREATE the Lambda (bootstrap image).
    After creation, image.yml rolls the running image via update-function-code
    and Terraform ignores image drift, so this only matters on a fresh create.
  EOT
  type    = string
  default = "951da7ab319f"
}

variable "function_url_auth_type" {
  description = "Function URL auth: AWS_IAM (signed callers only — safe default) or NONE (public; only with app-layer OAuth)."
  type        = string
  default     = "AWS_IAM"
}

variable "auth_mode" {
  description = "AFS_AUTH_MODE for the deployed app (\"dev\" until the OAuth resource server lands)."
  type        = string
  default     = "dev"
}
