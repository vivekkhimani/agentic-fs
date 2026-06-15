output "site_bucket" {
  description = "S3 bucket the site content is synced into."
  value       = aws_s3_bucket.site.bucket
}

output "distribution_id" {
  description = "CloudFront distribution id (for cache invalidations)."
  value       = aws_cloudfront_distribution.site.id
}

output "distribution_domain" {
  description = "CloudFront domain (the alias records point here)."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "certificate_arn" {
  description = "ACM certificate ARN (us-east-1)."
  value       = aws_acm_certificate.site.arn
}

output "deploy_role_arn" {
  description = "Role the CI deploy workflow assumes (S3 sync + CloudFront invalidation)."
  value       = aws_iam_role.deploy.arn
}

output "url" {
  description = "The live site URL."
  value       = "https://${var.domain}"
}
