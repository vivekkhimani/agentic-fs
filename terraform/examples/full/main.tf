# ---------------------------------------------------------------------------
# Full root — "show me everything". Composes every capability that exists today,
# production-tuned (deletion protection + PITR on the catalog, alarms with email).
#
# The optional CAPABILITY modules below aren't built yet — they're left as clear
# slots (not faked) and tracked as contribution issues (see README.md):
#   - search_bedrock_kb   (semantic fs_search over Bedrock Knowledge Base)
#   - compute_fargate + network   (always-on API behind an ALB in private subnets)
#   - auth_cognito        (batteries-included managed OAuth IdP)
# When a module lands it slots in here behind an `enable_*` flag, the same way the
# implemented modules are composed below.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

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

module "catalog" {
  source = "../../modules/catalog_dynamodb"

  name_prefix                    = var.name_prefix
  kms_key_arn                    = module.kms.key_arn
  deletion_protection_enabled    = true
  point_in_time_recovery_enabled = true
}

module "ecr" {
  source = "../../modules/ecr_mirror"

  name_prefix = var.name_prefix
}

data "terraform_remote_state" "ci_roles" {
  backend = "s3"
  config = {
    bucket = "agentic-fs-terraform-state-${var.aws_account_id}"
    key    = "global/ci-roles.tfstate"
    region = "us-east-1"
  }
}

module "compute" {
  source = "../../modules/compute_lambda"

  name_prefix              = var.name_prefix
  image_uri                = "${module.ecr.repository_url}:${var.image_tag}"
  region                   = var.aws_region
  data_bucket_name         = module.storage.bucket_name
  data_bucket_arn          = module.storage.bucket_arn
  catalog_table_name       = module.catalog.table_name
  catalog_table_arn        = module.catalog.table_arn
  kms_key_arn              = module.kms.key_arn
  permissions_boundary_arn = data.terraform_remote_state.ci_roles.outputs.permissions_boundary_arn
  function_url_auth_type   = "AWS_IAM"
  auth_mode                = var.auth_mode
}

module "ingestion" {
  source = "../../modules/ingestion"

  name_prefix              = var.name_prefix
  image_uri                = "${module.ecr.repository_url}:worker-${var.image_tag}"
  region                   = var.aws_region
  data_bucket_name         = module.storage.bucket_name
  data_bucket_arn          = module.storage.bucket_arn
  catalog_table_name       = module.catalog.table_name
  catalog_table_arn        = module.catalog.table_arn
  kms_key_arn              = module.kms.key_arn
  permissions_boundary_arn = data.terraform_remote_state.ci_roles.outputs.permissions_boundary_arn
}

module "observability" {
  source = "../../modules/observability"

  name_prefix              = var.name_prefix
  kms_key_arn              = module.kms.key_arn
  alarm_email              = var.alarm_email
  api_function_name        = module.compute.function_name
  worker_function_name     = module.ingestion.worker_function_name
  reconciler_function_name = module.ingestion.reconciler_function_name
  extract_queue_name       = module.ingestion.queue_name
  dlq_name                 = module.ingestion.dlq_name
  catalog_table_name       = module.catalog.table_name
}

# --- optional capability modules (not yet built — see README + issues) -------
# module "search" { source = "../../modules/search_bedrock_kb"  ... }   # semantic fs_search
# module "network" { source = "../../modules/network" ... }            # private subnets / NAT
# module "compute_fargate" { source = "../../modules/compute_fargate" ... }  # always-on API
# module "auth" { source = "../../modules/auth_cognito" ... }          # managed OAuth IdP
