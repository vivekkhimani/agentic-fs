provider "aws" {
  region = var.aws_region

  # Guard against running against the wrong account. Terraform fails fast if
  # the resolved credentials don't belong to this account.
  allowed_account_ids = [var.aws_account_id]

  # Every agentic-fs resource carries these tags so the whole footprint is
  # discoverable (and tearable-down) by tag. See terraform/README.md#teardown.
  default_tags {
    tags = {
      Project   = "agentic-fs"
      ManagedBy = "terraform"
      Repo      = "agentic-fs"
      Component = "tf-state-backend"
      Env       = "global"
    }
  }
}
