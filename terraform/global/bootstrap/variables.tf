variable "aws_account_id" {
  description = "AWS account ID that hosts agentic-fs infrastructure (shared with the existing Seamind account during the trial phase)."
  type        = string
  default     = "002988089284"
}

variable "aws_region" {
  description = "AWS region for the Terraform state bucket."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = <<-EOT
    Name of the S3 bucket that stores remote Terraform state for every
    agentic-fs root module. Account-suffixed for global uniqueness. This value
    is referenced verbatim in each root's backend block — keep them in sync.
  EOT
  type        = string
  default     = "agentic-fs-terraform-state-002988089284"
}
