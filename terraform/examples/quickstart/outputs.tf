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

output "region" {
  description = "AWS region this footprint is deployed into."
  value       = var.aws_region
}

output "name_prefix" {
  description = "Resource name prefix in effect for this root."
  value       = var.name_prefix
}
