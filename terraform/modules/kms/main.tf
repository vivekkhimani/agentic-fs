# ---------------------------------------------------------------------------
# Project CMK
#
# The shared customer-managed key for SSE-KMS across the data bucket (and, as
# they land, the catalog table and derived data). Default footprint = ONE shared
# key (~$1/mo) with bucket keys enabled on consumers to cut KMS request cost.
#
# Per-tenant keys (`per_tenant_kms`, plan §4.3) are deferred: v1 ships the
# key-policy template + the app-side `tenant -> key_id` seam, but the automated
# key-fleet lifecycle is control-plane-shaped, not Terraform-shaped. This module
# will gain a `per_tenant_kms` flag + a `for_each` key fleet when that lands.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} project CMK — SSE-KMS for the data bucket and derived stores."
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.key.json
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}-data"
  target_key_id = aws_kms_key.this.key_id
}

# Key policy = account root holds full control; all other grants (S3 SSE on
# behalf of writers, future compute/ingestion roles) are delegated through IAM
# policies on those principals. This is the AWS-recommended default that keeps
# the key from being orphaned and lets IAM be the single place authority is
# granted.
data "aws_iam_policy_document" "key" {
  statement {
    sid       = "EnableRootAccountAdmin"
    effect    = "Allow"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  # Let CloudWatch alarms publish to SNS topics encrypted with this CMK (the
  # observability alerts topic). The cross-service publisher is the one principal
  # that can't be granted via IAM — it needs a key-policy grant — so it lives
  # here, scoped to this account. CloudWatch only wraps a data key to deliver an
  # alarm notification; it never receives document plaintext. Without this,
  # alarms would fire but notifications would silently fail to deliver.
  statement {
    sid       = "AllowCloudWatchAlarmsToUseKeyForEncryptedSns"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey*"]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}
