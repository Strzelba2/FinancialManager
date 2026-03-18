locals {
  stock_image = "${module.ecr.repository_urls["fm-stock"]}:${var.image_tag}"
}

module "stock" {
  source = "./modules/stock"

  enable = var.enable_services

  domain_name         = local.domain_name
  cluster_id          = aws_ecs_cluster.this.id
  execution_role_arn  = aws_iam_role.ecs_task_execution.arn
  task_role_arn       = aws_iam_role.ecs_task_app.arn

  subnets            = module.network.private_app_subnet_ids
  security_group_ids = [module.network.sg_services_id]

  image = local.stock_image

  rds_master_secret_arn = aws_secretsmanager_secret.rds_master[0].arn
  redis_endpoint = aws_elasticache_replication_group.redis[0].primary_endpoint_address

  tags = local.common_tags
}