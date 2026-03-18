variable "image_tag" {
  description = "Immutable image tag (git sha) pushed to ECR"
  type        = string
}


locals {
  niceui_image = "${module.ecr.repository_urls["fm-nice-ui"]}:${var.image_tag}"

  redis_endpoint = var.enable_redis ? aws_elasticache_replication_group.redis[0].primary_endpoint_address : null
}

module "nice_ui" {
  source = "./modules/nice_ui"

  enable             = var.enable_niceui
  cluster_id         = aws_ecs_cluster.this.id
  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task_app.arn
  subnets            = module.network.private_app_subnet_ids
  security_group_ids = [module.network.sg_services_id]

  image       = local.niceui_image
  domain_name = local.domain_name

  secret_key      = var.niceui_secret_key
  enable_redis    = var.enable_redis
  redis_endpoint  = local.redis_endpoint
  redis_db        = var.redis_db

  tags = local.common_tags
}