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
#   agentic-fs-terraform-apply  read (ReadOnlyAccess) + a SCOPED set of writes
#                               for the resource types Terraform actually
#                               manages (widened per milestone). Assumable ONLY
#                               from the gated `sandbox` GitHub Environment.
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

locals {
  repo_sub = "repo:${var.github_org}/${var.github_repo}"
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
# Apply role (read + scoped write, environment-gated)
# ===========================================================================
resource "aws_iam_role" "apply" {
  name                 = "agentic-fs-terraform-apply"
  description          = "Terraform CI apply role: read + scoped write. Assumable only from the gated `sandbox` GitHub Environment."
  assume_role_policy   = data.aws_iam_policy_document.apply_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "apply_readonly" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "apply_state" {
  name   = "terraform-state-backend"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.state_backend.json
}

# --- Scoped infra WRITES for the apply role (widened one milestone at a time) ---
#
# The skeleton manages no application resources yet — `examples/quickstart` is an
# empty root — so the apply role needs only ReadOnlyAccess + state access above.
#
# As each module lands (M0: storage/kms; M1: catalog_dynamodb/compute_lambda;
# …), add ONLY that module's mutating actions here, scoped by ARN/prefix, and
# re-apply this root. Never widen to `s3:*` / `*`. Example shape for the storage
# module (commented until the module exists):
#
# data "aws_iam_policy_document" "apply_writes" {
#   statement {
#     sid    = "ManageDataBucket"
#     effect = "Allow"
#     actions = [
#       "s3:CreateBucket",
#       "s3:PutBucketTagging",
#       "s3:PutBucketPolicy",
#       "s3:PutBucketVersioning",
#       "s3:PutEncryptionConfiguration",
#       "s3:PutLifecycleConfiguration",
#       "s3:PutBucketNotification",
#       "s3:PutBucketPublicAccessBlock",
#     ]
#     resources = ["arn:aws:s3:::agentic-fs-data-*"]
#   }
# }
#
# resource "aws_iam_role_policy" "apply_writes" {
#   name   = "terraform-managed-writes"
#   role   = aws_iam_role.apply.id
#   policy = data.aws_iam_policy_document.apply_writes.json
# }
