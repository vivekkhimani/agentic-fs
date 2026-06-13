output "plan_role_arn" {
  description = "ARN of the read-only Terraform plan/drift role — used by PR plan + drift workflows."
  value       = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  description = "ARN of the sandbox-gated Terraform apply role — used by apply jobs only."
  value       = aws_iam_role.apply.arn
}

output "permissions_boundary_arn" {
  description = "ARN of the agentic-fs CI permissions boundary. Any IAM role created by a module (e.g. a Lambda exec role) MUST set permissions_boundary to this, or the apply role's boundary will deny its creation."
  value       = aws_iam_policy.ci_boundary.arn
}
