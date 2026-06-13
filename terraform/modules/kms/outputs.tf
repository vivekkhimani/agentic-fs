output "key_arn" {
  description = "ARN of the project CMK — pass to modules that configure SSE-KMS (storage, catalog)."
  value       = aws_kms_key.this.arn
}

output "key_id" {
  description = "Key id of the project CMK."
  value       = aws_kms_key.this.key_id
}

output "alias_arn" {
  description = "ARN of the key alias."
  value       = aws_kms_alias.this.arn
}
