output "queue_arn" {
  description = "ARN of the extract queue."
  value       = aws_sqs_queue.extract.arn
}

output "queue_url" {
  description = "URL of the extract queue."
  value       = aws_sqs_queue.extract.id
}

output "queue_name" {
  description = "Name of the extract queue (the CloudWatch QueueName dimension)."
  value       = aws_sqs_queue.extract.name
}

output "dlq_arn" {
  description = "ARN of the dead-letter queue (poison messages land here)."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_name" {
  description = "Name of the dead-letter queue (the CloudWatch QueueName dimension)."
  value       = aws_sqs_queue.dlq.name
}

output "worker_function_name" {
  description = "Name of the extractor worker Lambda."
  value       = aws_lambda_function.worker.function_name
}

output "worker_function_arn" {
  description = "ARN of the extractor worker Lambda."
  value       = aws_lambda_function.worker.arn
}

output "reconciler_function_name" {
  description = "Name of the reconciler Lambda."
  value       = aws_lambda_function.reconciler.function_name
}

output "reconciler_function_arn" {
  description = "ARN of the reconciler Lambda."
  value       = aws_lambda_function.reconciler.arn
}
