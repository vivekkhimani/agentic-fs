# ---------------------------------------------------------------------------
# Quickstart root — the default, near-$0-idle agentic-fs footprint.
#
# Composes the modules implemented so far. As later modules land (catalog,
# ingestion, compute, auth, observability) they are wired in here the same way.
# ---------------------------------------------------------------------------

# Resolves (and, via allowed_account_ids, guards) the target account. Also the
# global-uniqueness suffix for bucket/table names.
data "aws_caller_identity" "current" {}

# M0 — the foundation: the project CMK and the canonical data bucket.
module "kms" {
  source = "../../modules/kms"

  name_prefix = var.name_prefix
}

module "storage" {
  source = "../../modules/storage"

  name_prefix = var.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
  kms_key_arn = module.kms.key_arn
}
