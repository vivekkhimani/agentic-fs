provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project   = "agentic-fs"
      ManagedBy = "terraform"
      Repo      = "agentic-fs"
      Example   = "full"
      Env       = var.env
    }
  }
}
