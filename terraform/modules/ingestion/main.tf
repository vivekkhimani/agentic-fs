# ---------------------------------------------------------------------------
# Ingestion pipeline — async extraction (ADR 0009).
#
# The data bucket already emits to EventBridge (storage module). A rule selects
# object-created events under `tenants/` (originals only — derived/scratch writes
# are excluded for free) and fans them to SQS; the docling extractor worker
# Lambda drains the queue, reads the original from S3, runs the pipeline, and
# writes the derived pages + flips the catalog row. Failures past
# max_receive_count land in the DLQ.
# ---------------------------------------------------------------------------

locals {
  worker_name = "${var.name_prefix}-worker"
}

# --- queues (SSE-SQS: AWS-managed keys, so EventBridge needs no CMK grant) ---
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-extract-dlq"
  message_retention_seconds = 1209600 # 14 days — room to inspect poison messages
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "extract" {
  name = "${var.name_prefix}-extract"
  # Visibility must exceed the function timeout; AWS guidance is ~6x to absorb retries.
  visibility_timeout_seconds = var.timeout_seconds * 6
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

data "aws_iam_policy_document" "queue" {
  statement {
    sid       = "AllowEventBridge"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.extract.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.object_created.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "extract" {
  queue_url = aws_sqs_queue.extract.id
  policy    = data.aws_iam_policy_document.queue.json
}

# Lock the DLQ down to *only* receive failures from the extract queue, and allow
# a redrive (move messages back to extract) once a poison cause is fixed — the
# operator runs `aws sqs start-message-move-task` against this DLQ. Without this
# allow-policy the DLQ would accept redrive from any queue in the account.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.extract.arn]
  })
}

# --- EventBridge: S3 object-created under tenants/ -> the queue ---
resource "aws_cloudwatch_event_rule" "object_created" {
  name        = "${var.name_prefix}-object-created"
  description = "Data-bucket originals (tenants/) object-created -> extract queue"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [var.data_bucket_name] }
      object = { key = [{ prefix = "tenants/" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "to_queue" {
  rule = aws_cloudwatch_event_rule.object_created.name
  arn  = aws_sqs_queue.extract.arn
}

# --- worker execution role (least-privilege, boundary-capped) ---
data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name                 = "${local.worker_name}-exec"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.worker_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.worker.arn}:*"]
  }
  # Read the original document, write its derived-text pages.
  statement {
    sid       = "ReadOriginals"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/*"]
  }
  statement {
    sid       = "WriteDerived"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.data_bucket_arn}/*"]
  }
  # Read the row, upsert it, set the extraction state.
  statement {
    sid    = "Catalog"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [var.catalog_table_arn, "${var.catalog_table_arn}/index/*"]
  }
  # SSE-KMS for the S3 reads (Decrypt) and derived writes (GenerateDataKey).
  statement {
    sid       = "UseCmk"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
  # OCR for scanned pages (the textract rung). detect_document_text is resourceless
  # in Textract's IAM model, so it can't be scoped to an ARN.
  statement {
    sid       = "TextractOcr"
    effect    = "Allow"
    actions   = ["textract:DetectDocumentText"]
    resources = ["*"]
  }
  # Drain the queue (the event-source mapping).
  statement {
    sid       = "ConsumeQueue"
    effect    = "Allow"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.extract.arn]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "agentic-fs-worker"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

# --- worker Lambda ---
resource "aws_lambda_function" "worker" {
  function_name = local.worker_name
  role          = aws_iam_role.worker.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = var.memory_mb
  timeout       = var.timeout_seconds

  environment {
    variables = {
      AFS_REGION               = var.region
      AFS_OBJECT_STORE_BACKEND = "s3"
      AFS_DATA_BUCKET          = var.data_bucket_name
      AFS_CATALOG_BACKEND      = "dynamodb"
      AFS_CATALOG_TABLE        = var.catalog_table_name
      AFS_KMS_KEY_ARN          = var.kms_key_arn
      AFS_EXTRACTION_LADDER    = var.extraction_ladder
      AFS_LOG_LEVEL            = var.log_level
    }
  }

  depends_on = [aws_iam_role_policy.worker, aws_cloudwatch_log_group.worker]

  # Continuous deployment owns the running image (image.yml rolls worker-<sha>);
  # Terraform sets the bootstrap image and then ignores image drift.
  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_lambda_event_source_mapping" "worker" {
  event_source_arn = aws_sqs_queue.extract.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = var.batch_size
}
