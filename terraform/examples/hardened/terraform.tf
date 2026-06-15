terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # PARTIAL backend config — supply the account-specific bucket at init:
  #   terraform init -backend-config="bucket=agentic-fs-terraform-state-<account_id>"
  backend "s3" {
    key          = "examples/hardened.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
