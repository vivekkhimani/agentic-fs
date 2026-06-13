# ---------------------------------------------------------------------------
# Catalog (DynamoDB — default CatalogStore)
#
# A single-table design (plan §5.1) holding documents, control records
# (tenants/namespaces/principals), connector checkpoints, scratch usage, and
# idempotency locks. The catalog is a DERIVED INDEX of S3 — healable from the
# bucket by the reconciler — so it carries PITR + deletion protection to make
# loss recoverable, but it is never the source of truth.
#
# Physical keys are generic (PK/SK + GSI keys); the value schemes
# (`T#{tenant}#NS#{ns}`, `T#{tenant}#DOC#{doc_id}`, …) live in the app's
# CatalogStore implementation, not here.
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "catalog" {
  name         = "${var.name_prefix}-catalog"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "PK"
  range_key = "SK"

  deletion_protection_enabled = var.deletion_protection_enabled

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }

  # GSI1 — by_doc: resolve a doc_id to its item(s) (`T#{tenant}#DOC#{doc_id}`).
  attribute {
    name = "GSI1PK"
    type = "S"
  }

  # GSI2 — by_checksum: dedupe / idempotency (`T#{tenant}#SHA#{sha256}`).
  attribute {
    name = "GSI2PK"
    type = "S"
  }

  # GSI3 — by_extraction_status: SPARSE. The app writes these attributes only
  # while status ∈ {pending, extracting, failed, catalog_only} and removes them
  # on success, so the index stays tiny and powers ops queries ("all failed",
  # "stuck > 1h" via the timestamp range key).
  attribute {
    name = "GSI3PK"
    type = "S"
  }
  attribute {
    name = "GSI3SK"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1_by_doc"
    projection_type = "ALL"

    key_schema {
      attribute_name = "GSI1PK"
      key_type       = "HASH"
    }
  }

  global_secondary_index {
    name            = "gsi2_by_checksum"
    projection_type = "ALL"

    key_schema {
      attribute_name = "GSI2PK"
      key_type       = "HASH"
    }
  }

  global_secondary_index {
    name            = "gsi3_by_extraction_status"
    projection_type = "ALL"

    key_schema {
      attribute_name = "GSI3PK"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "GSI3SK"
      key_type       = "RANGE"
    }
  }

  # TTL drives expiry of idempotency locks and other ephemeral items.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery_enabled
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }
}
