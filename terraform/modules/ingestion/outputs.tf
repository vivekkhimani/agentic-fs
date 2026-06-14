output "queue_arn" {
  description = "ARN of the extract queue."
  value       = aws_sqs_queue.extract.arn
}

output "queue_url" {
  description = "URL of the extract queue."
  value       = aws_sqs_queue.extract.id
}

output "dlq_arn" {
  description = "ARN of the dead-letter queue (poison messages land here)."
  value       = aws_sqs_queue.dlq.arn
}

output "worker_function_name" {
  description = "Name of the extractor worker Lambda."
  value       = aws_lambda_function.worker.function_name
}

output "worker_function_arn" {
  description = "ARN of the extractor worker Lambda."
  value       = aws_lambda_function.worker.arn
}
