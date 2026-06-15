terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Local state by default — this is a tiny, rarely-changed personal site and it
  # must NOT depend on the agentic-fs state bucket (which a full teardown removes).
  # Switch to an S3 backend later if you want shared state.
}
