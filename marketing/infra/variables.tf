variable "domain" {
  description = "Apex domain for the marketing site (a Route 53 public hosted zone must already exist)."
  type        = string
  default     = "agenticfs.xyz"
}

variable "github_repo" {
  description = "owner/repo allowed to assume the CI deploy role (OIDC sub scope)."
  type        = string
  default     = "vivekkhimani/agentic-fs"
}
