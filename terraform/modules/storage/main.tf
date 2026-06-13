# ---------------------------------------------------------------------------
# Data bucket
#
# The single canonical store (plan §3). One bucket, channel-first keys:
#   tenants/   raw canonical documents (source of truth)
#   derived/   extracted text + manifests + tree artifacts (rebuildable)
#   scratch/   agent scratch space (TTL'd, never indexed)
#
# S3 is canonical; everything else is healable from it — so this bucket is
# versioned, KMS-encrypted, TLS-only, and private.
# ---------------------------------------------------------------------------

locals {
  bucket_name = "${var.name_prefix}-data-${var.account_id}"
}

resource "aws_s3_bucket" "data" {
  bucket = local.bucket_name

  tags = {
    Name = local.bucket_name
  }
}

# ACLs disabled — ownership is the only access model.
resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Raw is canonical — versioning protects against deletion/overwrite bugs.
resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-KMS with the project CMK; bucket keys enabled cut KMS request cost ~99%.
resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

# S3 -> EventBridge drives the (future) extract pipeline. One rule filtering on
# `tenants/` will feed extraction and excludes derived/scratch writes for free.
resource "aws_s3_bucket_notification" "data" {
  bucket      = aws_s3_bucket.data.id
  eventbridge = true
}

# Per-channel lifecycle (plan §3.3).
resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  # Clean up failed multipart uploads everywhere.
  rule {
    id     = "abort-multipart"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }

  # Scratch is ephemeral: expire current objects after the TTL, drop noncurrent
  # versions fast.
  rule {
    id     = "scratch-ttl"
    status = "Enabled"

    filter {
      prefix = "scratch/"
    }

    expiration {
      days = var.scratch_ttl_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  # Derived data is rebuildable — keep noncurrent versions only briefly.
  rule {
    id     = "derived-noncurrent"
    status = "Enabled"

    filter {
      prefix = "derived/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  # Canonical documents — retain noncurrent versions for the configured window.
  rule {
    id     = "tenants-noncurrent"
    status = "Enabled"

    filter {
      prefix = "tenants/"
    }

    noncurrent_version_expiration {
      noncurrent_days = var.tenants_noncurrent_days
    }
  }

  # Optional: tier canonical documents to Intelligent-Tiering.
  dynamic "rule" {
    for_each = var.enable_intelligent_tiering ? [1] : []

    content {
      id     = "tenants-intelligent-tiering"
      status = "Enabled"

      filter {
        prefix = "tenants/"
      }

      transition {
        days          = 0
        storage_class = "INTELLIGENT_TIERING"
      }
    }
  }

  depends_on = [aws_s3_bucket_versioning.data]
}

resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id
  policy = data.aws_iam_policy_document.data.json

  # A policy can be rejected by BlockPublicPolicy evaluation if the PAB isn't in
  # place first; order the dependency explicitly.
  depends_on = [aws_s3_bucket_public_access_block.data]
}

data "aws_iam_policy_document" "data" {
  # TLS-only.
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/*"]

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

  # Force SSE-KMS on upload (a PUT without the aws:kms header is rejected).
  statement {
    sid       = "DenyUnencryptedObjectUploads"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.data.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms"]
    }
  }

  # Quarantine: when GuardDuty scanning is enabled, deny reads of objects tagged
  # with a malware finding to everyone except the scanner/extractor roles.
  dynamic "statement" {
    for_each = length(var.quarantine_exempt_role_arns) > 0 ? [1] : []

    content {
      sid       = "DenyAccessToQuarantinedObjects"
      effect    = "Deny"
      actions   = ["s3:GetObject"]
      resources = ["${aws_s3_bucket.data.arn}/*"]

      principals {
        type        = "*"
        identifiers = ["*"]
      }

      condition {
        test     = "StringEquals"
        variable = "s3:ExistingObjectTag/GuardDutyMalwareScanStatus"
        values   = ["THREATS_FOUND"]
      }

      condition {
        test     = "ArnNotLike"
        variable = "aws:PrincipalArn"
        values   = var.quarantine_exempt_role_arns
      }
    }
  }
}
