# ---------------------------------------------------------------------------
# Quickstart root — the default, near-$0-idle agentic-fs footprint.
#
# This is currently a SKELETON: it wires the backend, provider, tagging, and a
# caller-identity lookup, but composes no modules yet — the module directories
# under ../../modules are still scaffolds (plan §15). `terraform plan` here
# therefore reports "no changes", which is exactly what the CI pipeline asserts
# while the guardrails are validated end-to-end before any real resource lands.
#
# As modules are implemented they are composed below, e.g.:
#
#   module "kms" {
#     source      = "../../modules/kms"
#     name_prefix = var.name_prefix
#   }
#
#   module "storage" {
#     source      = "../../modules/storage"
#     name_prefix = var.name_prefix
#     kms_key_arn = module.kms.key_arn
#   }
#
#   module "catalog_dynamodb" {
#     source      = "../../modules/catalog_dynamodb"
#     name_prefix = var.name_prefix
#     kms_key_arn = module.kms.key_arn
#   }
#   # … ingestion, compute_lambda, auth_cognito, observability
#
# Each addition is paired with a matching widening of the apply role's
# `apply_writes` scope in ../../global/ci-roles.
# ---------------------------------------------------------------------------

# Resolves (and, via allowed_account_ids, guards) the target account. Also the
# global-uniqueness suffix for bucket/table names once modules land.
data "aws_caller_identity" "current" {}
