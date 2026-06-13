output "state_bucket_name" {
  description = "Name of the S3 bucket holding remote Terraform state. Use this in each root's backend block."
  value       = aws_s3_bucket.tf_state.id
}

output "state_bucket_arn" {
  description = "ARN of the state bucket — the CI roles get read/write + lock access to this in the OIDC policy."
  value       = aws_s3_bucket.tf_state.arn
}
