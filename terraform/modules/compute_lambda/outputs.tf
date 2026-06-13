output "function_url" {
  description = "The streaming Function URL serving the API."
  value       = aws_lambda_function_url.api.function_url
}

output "function_name" {
  description = "Name of the API Lambda function."
  value       = aws_lambda_function.api.function_name
}

output "function_arn" {
  description = "ARN of the API Lambda function."
  value       = aws_lambda_function.api.arn
}

output "exec_role_arn" {
  description = "ARN of the Lambda execution role."
  value       = aws_iam_role.exec.arn
}
