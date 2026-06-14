# ---------------------------------------------------------------------------
# CI identities for Terraform (GitHub OIDC)
#
# Two roles, following least-privilege + plan/apply separation:
#
#   agentic-fs-terraform-plan   read-only. Used by PR `plan` and scheduled
#                               drift. Cannot mutate infrastructure by
#                               construction. Assumable from any job in this
#                               repo (so fork-PR plans work — they get no write
#                               power).
#
#   agentic-fs-terraform-apply  read (ReadOnlyAccess) + broad writes
#                               (PowerUserAccess + scoped IAM writes), capped by
#                               the agentic-fs-ci-boundary permissions boundary.
#                               Assumable ONLY from the gated `sandbox` GitHub
#                               Environment. The boundary — not action
#                               enumeration — is what keeps this safe (region
#                               lock, state-bucket protection, no self-IAM
#                               escalation, created roles must inherit it).
#
# Both roles get read/write + lock access to the state bucket only.
#
# Reads for both roles come from the AWS-managed ReadOnlyAccess policy — broad
# on the read side (so a plan never fails on a missing read permission), tight
# on the write side, which is the part that matters.
#
# The GitHub OIDC provider already exists in this account (shared, created by
# the existing Seamind bootstrap); we reference it as a data source rather than
# creating a second one. Trust is per-role, so a new role for this repo is all
# that is required.
# ---------------------------------------------------------------------------

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_caller_identity" "current" {}

locals {
  repo_sub   = "repo:${var.github_org}/${var.github_repo}"
  account_id = data.aws_caller_identity.current.account_id

  # Constructed (not resource-attribute) ARNs so the boundary policy document can
  # reference the boundary's own ARN without creating a dependency cycle.
  boundary_arn     = "arn:aws:iam::${local.account_id}:policy/agentic-fs-ci-boundary"
  state_bucket_arn = "arn:aws:s3:::${var.state_bucket_name}"
  ci_identity_arns = [
    "arn:aws:iam::${local.account_id}:role/agentic-fs-terraform-plan",
    "arn:aws:iam::${local.account_id}:role/agentic-fs-terraform-apply",
    local.boundary_arn,
  ]
}

# --- Trust: plan role — any job in this repo (PRs incl. forks, scheduled drift) ---
data "aws_iam_policy_document" "plan_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo_sub}:*"]
    }
  }
}

# --- Trust: apply role — only jobs running in the gated `sandbox` Environment ---
# GitHub sets the OIDC subject to `repo:ORG/REPO:environment:NAME` when a job
# declares `environment:`, so this restricts the write role to the gated path.
data "aws_iam_policy_document" "apply_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo_sub}:environment:${var.apply_environment}"]
    }
  }
}

# --- State backend access (both roles): read state, write state + lockfile ---
data "aws_iam_policy_document" "state_backend" {
  statement {
    sid       = "StateBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}"]
  }

  statement {
    sid       = "StateObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket_name}/*"]
  }
}

# ===========================================================================
# Plan role (read-only)
# ===========================================================================
resource "aws_iam_role" "plan" {
  name                 = "agentic-fs-terraform-plan"
  description          = "Read-only Terraform CI role for plan + drift (PR and scheduled)."
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "plan_state" {
  name   = "terraform-state-backend"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.state_backend.json
}

# ===========================================================================
# Apply role (read + broad-but-bounded write, environment-gated)
#
# Permission model (chosen over per-action enumeration to avoid touching this
# root every milestone):
#   identity = ReadOnlyAccess  (all reads, incl. IAM reads)
#            + PowerUserAccess  (all non-IAM writes)
#            + agentic-fs-iam-writes  (IAM writes, scoped to agentic-fs-* only)
#   boundary = agentic-fs-ci-boundary  (the hard cap — see below)
#
# Effective authority = identity ∩ boundary. The boundary is what makes the
# broad identity safe: it denies anything outside the project's blast radius,
# denies the role touching its own identity or the state bucket, and forces any
# role this role CREATES to carry the same boundary (escalation prevention).
# ===========================================================================
resource "aws_iam_role" "apply" {
  name                 = "agentic-fs-terraform-apply"
  description          = "Terraform CI apply role: read + bounded write. Assumable only from the gated `sandbox` GitHub Environment."
  assume_role_policy   = data.aws_iam_policy_document.apply_trust.json
  max_session_duration = 3600
  permissions_boundary = aws_iam_policy.ci_boundary.arn
}

resource "aws_iam_role_policy_attachment" "apply_readonly" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "apply_poweruser" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

resource "aws_iam_role_policy" "apply_state" {
  name   = "terraform-state-backend"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.state_backend.json
}

# --- IAM writes the apply role needs (PowerUserAccess excludes all of iam:*) ---
# Scoped to agentic-fs-* identities so Terraform can manage app roles/policies
# (e.g. the Lambda exec role, the tenant-scoped role) but nothing else. Creating
# a role additionally requires attaching the project boundary (the boundary's
# escalation-prevention deny enforces this; the condition here is belt-and-braces).
data "aws_iam_policy_document" "apply_iam_writes" {
  statement {
    sid    = "ManageAgenticFsIdentities"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:UpdateRole",
      "iam:UpdateRoleDescription",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePermissionsBoundary",
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:TagPolicy",
      "iam:UntagPolicy",
      "iam:CreateInstanceProfile",
      "iam:DeleteInstanceProfile",
      "iam:AddRoleToInstanceProfile",
      "iam:RemoveRoleFromInstanceProfile",
      "iam:TagInstanceProfile",
      "iam:UntagInstanceProfile",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/agentic-fs-*",
      "arn:aws:iam::${local.account_id}:policy/agentic-fs-*",
      "arn:aws:iam::${local.account_id}:instance-profile/agentic-fs-*",
    ]
  }

  # PassRole — Terraform must hand app roles to the services that run them
  # (Lambda, ECS, etc.). Scoped to agentic-fs-* roles only.
  statement {
    sid       = "PassAgenticFsRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/agentic-fs-*"]
  }

  # Service-linked roles (ALB/ECS/etc.) have AWS-controlled names; allow create
  # only, on the service-linked path.
  statement {
    sid       = "ServiceLinkedRoles"
    effect    = "Allow"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/aws-service-role/*"]
  }
}

resource "aws_iam_role_policy" "apply_iam_writes" {
  name   = "agentic-fs-iam-writes"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.apply_iam_writes.json
}

# ===========================================================================
# Permissions boundary — the hard cap on the apply role
#
# Pattern: allow everything, then DENY the dangerous edges. Effective authority
# of the apply role can never exceed this, regardless of how broad its identity
# policies are.
# ===========================================================================
data "aws_iam_policy_document" "ci_boundary" {
  # Ceiling: the boundary permits all; the denies below carve it back.
  statement {
    sid       = "AllowAllAsCeiling"
    effect    = "Allow"
    actions   = ["*"]
    resources = ["*"]
  }

  # (a) Region lock — deny regional actions outside the home region. Global
  # services (IAM, STS, CloudFront, Route 53, Organizations, …) have no region
  # and are excluded via not_actions so they keep working.
  statement {
    sid    = "DenyOutsideHomeRegion"
    effect = "Deny"
    not_actions = [
      "iam:*",
      "sts:*",
      "organizations:*",
      "account:*",
      "cloudfront:*",
      "route53:*",
      "route53domains:*",
      "support:*",
      "waf:*",
      "globalaccelerator:*",
      "budgets:*",
      "ce:*",
      "cur:*",
      "health:*",
      "shield:*",
      "trustedadvisor:*",
    ]
    resources = ["*"]
    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  # (b) Protect the state bucket — object read/write stays allowed (that's how
  # the backend works); deleting or reconfiguring the BUCKET is denied.
  statement {
    sid    = "DenyStateBucketReconfig"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:PutBucketPolicy",
      "s3:DeleteBucketPolicy",
      "s3:PutEncryptionConfiguration",
      "s3:PutBucketVersioning",
      "s3:PutBucketPublicAccessBlock",
      "s3:PutLifecycleConfiguration",
      "s3:PutBucketOwnershipControls",
    ]
    resources = [local.state_bucket_arn]
  }

  # (c) Self-protection — the apply role cannot modify the CI roles or this
  # boundary policy (so it can't detach its own cap or widen its own trust).
  statement {
    sid       = "DenyCiIdentitySelfEdit"
    effect    = "Deny"
    actions   = ["iam:*"]
    resources = local.ci_identity_arns
  }

  # (d) Escalation prevention — any role the apply role creates MUST carry this
  # same boundary, and the boundary can't be stripped or swapped for a weaker
  # one. Two statements cover "wrong boundary" and "no boundary at all".
  statement {
    sid    = "DenyCreateRoleWithWrongBoundary"
    effect = "Deny"
    actions = [
      "iam:CreateRole",
      "iam:PutRolePermissionsBoundary",
    ]
    resources = ["*"]
    condition {
      test     = "StringNotEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.boundary_arn]
    }
  }

  statement {
    sid    = "DenyCreateRoleWithoutBoundary"
    effect = "Deny"
    actions = [
      "iam:CreateRole",
    ]
    resources = ["*"]
    condition {
      test     = "Null"
      variable = "iam:PermissionsBoundary"
      values   = ["true"]
    }
  }

  statement {
    sid    = "DenyBoundaryRemovalAndHumanCreds"
    effect = "Deny"
    actions = [
      "iam:DeleteRolePermissionsBoundary",
      "iam:CreateUser",
      "iam:CreateAccessKey",
      "iam:CreateLoginProfile",
      "iam:UpdateLoginProfile",
    ]
    resources = ["*"]
  }

  # (e) Account/org/billing — never CI's job (PowerUserAccess already excludes
  # most of these; this is defense in depth).
  statement {
    sid    = "DenyAccountAndOrg"
    effect = "Deny"
    actions = [
      "organizations:*",
      "account:*",
      "aws-portal:*",
      "billing:*",
      "payments:*",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ci_boundary" {
  name        = "agentic-fs-ci-boundary"
  description = "Permissions boundary capping the agentic-fs Terraform apply role to the project's blast radius."
  policy      = data.aws_iam_policy_document.ci_boundary.json
}

# ===========================================================================
# Image-push role (CD) — least-privilege, environment-gated
#
# Used by image.yml to build + push the API image to ECR and roll the Lambda to
# it (aws lambda update-function-code). Scoped to exactly the agentic-fs-api
# repo + function — far narrower than the apply role. Same gated `sandbox` trust.
# ===========================================================================
locals {
  ecr_api_repo_arn    = "arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/agentic-fs-api"
  api_function_arn    = "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:agentic-fs-api"
  worker_function_arn = "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:agentic-fs-worker"
}

data "aws_iam_policy_document" "image_push" {
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # this action does not support resource scoping
  }

  statement {
    sid    = "EcrPushPull"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = [local.ecr_api_repo_arn]
  }

  statement {
    sid       = "RollLambda"
    effect    = "Allow"
    actions   = ["lambda:GetFunction", "lambda:UpdateFunctionCode"]
    resources = [local.api_function_arn, local.worker_function_arn]
  }
}

resource "aws_iam_role" "image_push" {
  name               = "agentic-fs-ci-image-push"
  description        = "CD role: build/push the API image to ECR + roll the Lambda. Assumable only from the gated sandbox environment."
  assume_role_policy = data.aws_iam_policy_document.apply_trust.json # same env:sandbox subject
}

resource "aws_iam_role_policy" "image_push" {
  name   = "agentic-fs-image-push"
  role   = aws_iam_role.image_push.id
  policy = data.aws_iam_policy_document.image_push.json
}
