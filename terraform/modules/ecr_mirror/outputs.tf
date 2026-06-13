output "repository_url" {
  description = "URL of the API ECR repository (push images here; the Lambda pulls from it)."
  value       = aws_ecr_repository.api.repository_url
}

output "repository_arn" {
  description = "ARN of the API ECR repository."
  value       = aws_ecr_repository.api.arn
}
