# ---------------------------------------------------------------------------
# Serving compute — the API as a container Lambda behind a streaming Function URL.
#
# The image (one image for Lambda + Fargate, ADR 0003) runs uvicorn; the AWS
# Lambda Web Adapter baked into it bridges Function URL invocations to the ASGI
# app. The exec role is least-privilege AND carries the project permissions
# boundary (the CI apply role's boundary denies creating a role without it).
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

# --- execution role ---
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

resource "aws_iam_role" "exec" {
  name                 = "${var.name_prefix}-api-exec"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  permissions_boundary = var.permissions_boundary_arn
}

data "aws_iam_policy_document" "exec" {
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  # Read path: list + ranged get on the data bucket.
  statement {
    sid       = "ReadDataBucket"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/*"]
  }
  statement {
    sid       = "ListDataBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.data_bucket_arn]
  }

  # Read path: catalog queries (table + GSIs).
  statement {
    sid    = "ReadCatalog"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
      "dynamodb:DescribeTable",
    ]
    resources = [var.catalog_table_arn, "${var.catalog_table_arn}/index/*"]
  }

  # Decrypt SSE-KMS objects with the project CMK.
  statement {
    sid       = "DecryptWithCmk"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "exec" {
  name   = "agentic-fs-api-read"
  role   = aws_iam_role.exec.id
  policy = data.aws_iam_policy_document.exec.json
}

# --- function ---
resource "aws_lambda_function" "api" {
  function_name = "${var.name_prefix}-api"
  role          = aws_iam_role.exec.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = var.memory_mb
  timeout       = var.timeout_seconds

  environment {
    variables = merge(
      {
        AFS_REGION               = var.region
        AFS_OBJECT_STORE_BACKEND = "s3"
        AFS_DATA_BUCKET          = var.data_bucket_name
        AFS_CATALOG_BACKEND      = "dynamodb"
        AFS_CATALOG_TABLE        = var.catalog_table_name
        AFS_KMS_KEY_ARN          = var.kms_key_arn
        AFS_AUTH_MODE            = var.auth_mode
      },
      var.extra_env,
    )
  }

  depends_on = [
    aws_iam_role_policy.exec,
    aws_cloudwatch_log_group.api,
  ]

  # Continuous deployment owns the running image: image.yml pushes a new tag and
  # rolls the function via `aws lambda update-function-code`. Terraform sets the
  # INITIAL image at creation and then ignores image drift so the two don't
  # revert each other (see .github/workflows/image.yml, docs/decisions/0004).
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# --- streaming Function URL ---
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = var.function_url_auth_type
  invoke_mode        = "RESPONSE_STREAM"
}
