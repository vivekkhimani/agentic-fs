variable "aws_account_id" {
  description = "AWS account ID that hosts agentic-fs infrastructure."
  type        = string
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
    is supplied to each root's backend at init (-backend-config="bucket=…").
    Convention: agentic-fs-terraform-state-<account_id>.
  EOT
  type        = string
}
