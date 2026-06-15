variable "aws_account_id" {
  description = "AWS account ID that hosts agentic-fs infrastructure."
  type        = string
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "github_org" {
  description = "GitHub organization (or user) that owns the repo — sets the OIDC subject scope."
  type        = string
  default     = "vivekkhimani"
}

variable "github_repo" {
  description = "GitHub repository name — sets the OIDC subject scope."
  type        = string
  default     = "agentic-fs"
}

variable "apply_environment" {
  description = <<-EOT
    Name of the GitHub Environment from which the apply role is assumable. The
    apply role's trust is restricted to `repo:ORG/REPO:environment:<this>`, so
    only jobs that declare `environment: <this>` (and pass its approval gate)
    can assume the write role. agentic-fs ships a single sandbox environment.
  EOT
  type        = string
  default     = "sandbox"
}

variable "state_bucket_name" {
  description = "Terraform remote-state bucket the CI roles need read/write + lock access to (convention: agentic-fs-terraform-state-<account_id>)."
  type        = string
}
