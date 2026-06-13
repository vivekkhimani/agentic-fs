output "plan_role_arn" {
  description = "ARN of the read-only Terraform plan/drift role — used by PR plan + drift workflows."
  value       = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  description = "ARN of the sandbox-gated Terraform apply role — used by apply jobs only."
  value       = aws_iam_role.apply.arn
}
