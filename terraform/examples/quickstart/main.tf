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

# M1 — the read-path index: the default DynamoDB catalog.
module "catalog" {
  source = "../../modules/catalog_dynamodb"

  name_prefix = var.name_prefix
  kms_key_arn = module.kms.key_arn
}

# M1 — serving compute: the API image repository + the Lambda behind a Function URL.
module "ecr" {
  source = "../../modules/ecr_mirror"

  name_prefix = var.name_prefix
}

# The Lambda exec role must inherit the CI permissions boundary; read its ARN
# from the ci-roles root's state rather than hardcoding it.
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
  count  = var.enable_compute ? 1 : 0

  name_prefix              = var.name_prefix
  image_uri                = "${module.ecr.repository_url}:${var.image_tag}"
  region                   = var.aws_region
  data_bucket_name         = module.storage.bucket_name
  data_bucket_arn          = module.storage.bucket_arn
  catalog_table_name       = module.catalog.table_name
  catalog_table_arn        = module.catalog.table_arn
  kms_key_arn              = module.kms.key_arn
  permissions_boundary_arn = data.terraform_remote_state.ci_roles.outputs.permissions_boundary_arn
  function_url_auth_type   = var.function_url_auth_type
  auth_mode                = var.auth_mode
  # async = the serving PUT stores a `pending` row; the worker extracts off the
  # S3 event (ADR 0009). Flip to "inline" to extract in-request (no worker).
  extra_env = { AFS_EXTRACTION_MODE = var.extraction_mode }
}

module "ingestion" {
  source = "../../modules/ingestion"
  count  = var.enable_ingestion ? 1 : 0

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
