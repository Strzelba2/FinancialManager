locals {
  ecr_repositories = {
    "fm-wallet"       = {}
    "fm-stock"        = {}
    "fm-session-auth" = {}
    "fm-nice-ui"      = {}
    "fm-pgadmin"      = {}
  }
}

module "ecr" {
  source = "./modules/ecr"

  repositories = local.ecr_repositories

  default_image_tag_mutability = "IMMUTABLE"
  default_scan_on_push         = true
  default_force_delete         = false

  untagged_expire_days = 7
  keep_last_images     = 10

  default_encryption_type = "AES256"
  default_kms_key_arn     = null

  enable_repository_policy = false

  tags = local.common_tags
}
