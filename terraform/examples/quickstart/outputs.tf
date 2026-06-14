# Operator-facing values. Extended as modules land (function_url, issuer/audience…).

output "account_id" {
  description = "AWS account this footprint is deployed into."
  value       = data.aws_caller_identity.current.account_id
}

output "data_bucket_name" {
  description = "Name of the canonical data bucket."
  value       = module.storage.bucket_name
}

output "data_bucket_arn" {
  description = "ARN of the canonical data bucket."
  value       = module.storage.bucket_arn
}

output "kms_key_arn" {
  description = "ARN of the project CMK."
  value       = module.kms.key_arn
}

output "catalog_table_name" {
  description = "Name of the DynamoDB catalog table."
  value       = module.catalog.table_name
}

output "catalog_table_arn" {
  description = "ARN of the DynamoDB catalog table."
  value       = module.catalog.table_arn
}

output "ecr_repository_url" {
  description = "Push the API image here (the Lambda pulls from it)."
  value       = module.ecr.repository_url
}

output "function_url" {
  description = "The API Function URL (null unless enable_compute = true)."
  value       = var.enable_compute ? module.compute[0].function_url : null
}

output "worker_function_name" {
  description = "The extractor worker Lambda (null unless enable_ingestion = true)."
  value       = var.enable_ingestion ? module.ingestion[0].worker_function_name : null
}

output "extract_queue_url" {
  description = "The extract SQS queue URL (null unless enable_ingestion = true)."
  value       = var.enable_ingestion ? module.ingestion[0].queue_url : null
}

output "region" {
  description = "AWS region this footprint is deployed into."
  value       = var.aws_region
}

output "name_prefix" {
  description = "Resource name prefix in effect for this root."
  value       = var.name_prefix
}
