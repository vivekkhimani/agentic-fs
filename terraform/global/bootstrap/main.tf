# ---------------------------------------------------------------------------
# Terraform remote state backend
#
# Creates the single S3 bucket used by every agentic-fs root (global + each
# example) as its `backend "s3"` store. State locking uses S3 native
# conditional writes (`use_lockfile = true`, Terraform >= 1.10) — no DynamoDB
# lock table needed.
#
# State holds sensitive material (secret ARNs, KMS key ids, and any secret
# values that land in state as modules are added), so the bucket is private,
# encrypted, versioned, and TLS-only. Treat deletion as catastrophic — it is
# protected accordingly.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "tf_state" {
  bucket = var.state_bucket_name

  # Losing this bucket means losing the state for ALL agentic-fs infrastructure.
  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name = var.state_bucket_name
  }
}

# Versioning lets us recover from a corrupted or accidentally-truncated state
# push by rolling back to a prior object version.
resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 (AES256), not SSE-KMS, is deliberate for the STATE bucket: a CMK here
# adds cost and a bootstrap dependency (the key would have to exist before the
# bucket that stores the key module's own state). The application *data* bucket
# (storage module) uses SSE-KMS with the project CMK per plan §3.3 — this
# exception is scoped to remote state only.
#trivy:ignore:AWS-0132
resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Expire noncurrent state versions so the bucket doesn't grow without bound,
# while keeping a generous recovery window.
resource "aws_s3_bucket_lifecycle_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    id     = "expire-noncurrent-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Deny any non-TLS access to state objects.
resource "aws_s3_bucket_policy" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  policy = data.aws_iam_policy_document.tf_state.json
}

data "aws_iam_policy_document" "tf_state" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.tf_state.arn, "${aws_s3_bucket.tf_state.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
