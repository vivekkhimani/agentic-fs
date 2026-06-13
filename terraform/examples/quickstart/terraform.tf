terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Remote state in the bootstrap-created bucket, one key per root.
  # Native S3 locking (use_lockfile) — no DynamoDB lock table.
  backend "s3" {
    bucket       = "agentic-fs-terraform-state-002988089284"
    key          = "examples/quickstart.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
