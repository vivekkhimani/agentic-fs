provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  # Tag the entire footprint so it is discoverable — and tearable-down — by tag.
  # See terraform/README.md#teardown.
  default_tags {
    tags = {
      Project   = "agentic-fs"
      ManagedBy = "terraform"
      Repo      = "agentic-fs"
      Example   = "quickstart"
      Env       = var.env
    }
  }
}
