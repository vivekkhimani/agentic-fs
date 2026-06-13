# Outputs are intentionally minimal while the root is a skeleton. As modules are
# composed, surface the operator-facing values here (e.g. function_url,
# data bucket name, issuer/audience) per the plan §11.1.

output "account_id" {
  description = "AWS account this footprint is deployed into."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS region this footprint is deployed into."
  value       = var.aws_region
}

output "name_prefix" {
  description = "Resource name prefix in effect for this root."
  value       = var.name_prefix
}
