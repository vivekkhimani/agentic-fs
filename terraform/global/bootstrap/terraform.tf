terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Chicken-and-egg: this config CREATES the S3 bucket that every other
  # agentic-fs Terraform root uses as its remote backend, so it cannot use that
  # backend on its own first apply. The local state file produced in step 1 is
  # never committed (it carries account metadata) — step 2 moves it into S3.
  #
  #   1. First apply with the default local backend (state in this dir).
  #   2. Uncomment the `backend "s3"` block below and re-run
  #      `terraform init -migrate-state` to move bootstrap's own state into the
  #      bucket it just created.
  #
  # See ./README.md for the exact command sequence.
  #
  # PARTIAL backend config — supply the account-specific bucket at migrate-init:
  #   terraform init -migrate-state -backend-config="bucket=agentic-fs-terraform-state-<account_id>"
  backend "s3" {
    key          = "global/bootstrap.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
