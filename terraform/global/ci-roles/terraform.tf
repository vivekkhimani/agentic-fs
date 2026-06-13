terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket       = "agentic-fs-terraform-state-002988089284"
    key          = "global/ci-roles.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
