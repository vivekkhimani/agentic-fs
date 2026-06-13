output "bucket_name" {
  description = "Name of the data bucket."
  value       = aws_s3_bucket.data.id
}

output "bucket_arn" {
  description = "ARN of the data bucket — pass to ingestion/compute modules and the apply role's scoping."
  value       = aws_s3_bucket.data.arn
}

output "bucket_regional_domain_name" {
  description = "Regional domain name of the data bucket (for presign/CDN wiring)."
  value       = aws_s3_bucket.data.bucket_regional_domain_name
}
