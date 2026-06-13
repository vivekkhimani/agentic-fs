# ---------------------------------------------------------------------------
# ECR — private repository for the agentic-fs API image.
#
# Lambda can only pull container images from ECR in the SAME account, so the
# published image is hosted here. (The "mirror" of upstream pinned images, per
# the module contract, is deferred — this implements the repo the API uses.)
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "api" {
  name                 = "${var.name_prefix}-api"
  image_tag_mutability = "IMMUTABLE" # each release is a new tag; never re-point a tag
  force_delete         = true        # sandbox convenience; tighten for production

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# Keep the repo small: expire untagged (superseded) images.
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_expiry_days
        }
        action = { type = "expire" }
      }
    ]
  })
}
