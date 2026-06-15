# ---------------------------------------------------------------------------
# Hardened root — quickstart composition with defense-in-depth dialed up on the
# modules that exist today:
#   - CMK deletion window maxed (30d)
#   - catalog: deletion protection + point-in-time recovery ON
#   - Function URL: AWS_IAM only (signed callers); app auth = OIDC resource server
#   - alarms with an email subscription
#
# Headline hardening that needs modules still to be built is intentionally left
# out (not faked) and tracked as contribution issues — see README.md:
#   - security_guardduty   (S3 malware scan + quarantine gate)
#   - storage access logs   (object-level S3 access logging)
#   - network + compute_fargate (private subnets / NAT, no public Function URL)
#   - per-request STS session scoping (Layer-2 tenant isolation)
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

module "kms" {
  source = "../../modules/kms"

  name_prefix             = var.name_prefix
  deletion_window_in_days = var.kms_deletion_window_in_days
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
  function_url_auth_type   = "AWS_IAM" # signed callers only — never NONE in hardened
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
