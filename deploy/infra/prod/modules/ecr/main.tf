data "aws_caller_identity" "current" {}

locals {
  default_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than ${var.untagged_expire_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.untagged_expire_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep last ${var.keep_last_images} images (tagged + untagged)"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.keep_last_images
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_ecr_repository" "this" {
  for_each = var.repositories

  name                 = each.key
  image_tag_mutability = coalesce(each.value.image_tag_mutability, var.default_image_tag_mutability)
  force_delete         = coalesce(each.value.force_delete, var.default_force_delete)

  image_scanning_configuration {
    scan_on_push = coalesce(each.value.scan_on_push, var.default_scan_on_push)
  }

  encryption_configuration {
    encryption_type = coalesce(try(each.value.encryption_type, null), var.default_encryption_type)

    kms_key = (
      coalesce(try(each.value.encryption_type, null), var.default_encryption_type) == "KMS"
      ? try(each.value.kms_key_arn, var.default_kms_key_arn)
      : null
    )
  }

  tags = var.tags

  lifecycle {
    precondition {
      condition = (
        coalesce(try(each.value.encryption_type, null), var.default_encryption_type) != "KMS"
        || try(each.value.kms_key_arn, var.default_kms_key_arn) != null
      )
      error_message = "ECR encryption_type=KMS requires kms_key_arn (per-repo) or default_kms_key_arn."
    }
  }
}
resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = var.repositories
  repository = aws_ecr_repository.this[each.key].name

  policy = coalesce(
    try(each.value.lifecycle_policy_json, null),
    local.default_lifecycle_policy
  )
}

data "aws_iam_policy_document" "repo_policy_default" {
  for_each = var.repositories

  statement {
    sid    = "AllowAccountPrincipalsRead"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchCheckLayerAvailability",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:ListImages"
    ]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_ecr_repository_policy" "this" {
  for_each = var.enable_repository_policy ? var.repositories : {}

  repository = aws_ecr_repository.this[each.key].name

  policy = coalesce(
    try(each.value.repository_policy_json, null),
    data.aws_iam_policy_document.repo_policy_default[each.key].json
  )
}