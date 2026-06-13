output "table_name" {
  description = "Name of the catalog table."
  value       = aws_dynamodb_table.catalog.name
}

output "table_arn" {
  description = "ARN of the catalog table — pass to compute/ingestion modules and IAM scoping."
  value       = aws_dynamodb_table.catalog.arn
}

output "table_stream_arn" {
  description = "DynamoDB stream ARN (null unless streams are enabled later for change capture)."
  value       = aws_dynamodb_table.catalog.stream_arn
}
