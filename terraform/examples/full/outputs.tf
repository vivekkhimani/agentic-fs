output "account_id" {
  description = "AWS account this footprint is deployed into."
  value       = data.aws_caller_identity.current.account_id
}

output "data_bucket_name" {
  description = "Name of the canonical data bucket."
  value       = module.storage.bucket_name
}

output "kms_key_arn" {
  description = "ARN of the project CMK."
  value       = module.kms.key_arn
}

output "catalog_table_name" {
  description = "Name of the DynamoDB catalog table."
  value       = module.catalog.table_name
}

output "ecr_repository_url" {
  description = "Push the API + worker images here."
  value       = module.ecr.repository_url
}

output "function_url" {
  description = "The API Function URL."
  value       = module.compute.function_url
}

output "alerts_topic_arn" {
  description = "SNS topic the CloudWatch alarms publish to."
  value       = module.observability.alerts_topic_arn
}

output "region" {
  description = "AWS region this footprint is deployed into."
  value       = var.aws_region
}
