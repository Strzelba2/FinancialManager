locals {
  session_auth_image = "${module.ecr.repository_urls["fm-session-auth"]}:${var.image_tag}"
}

variable "bootstrap_session_superuser" {
  type    = bool
  default = false
}

module "session_auth" {
  source = "./modules/session_auth"

  enable              = var.enable_services
  enable_celery       = true
  bootstrap_superuser = var.bootstrap_session_superuser

  cluster_id         = aws_ecs_cluster.this.id
  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task_app.arn

  subnets            = module.network.private_app_subnet_ids
  security_group_ids = [module.network.sg_services_id]

  image       = local.session_auth_image
  domain_name = local.domain_name

  rds_master_secret_arn    = aws_secretsmanager_secret.rds_master[0].arn
  redis_endpoint           = aws_elasticache_replication_group.redis[0].primary_endpoint_address
  session_auth_secret_arn  = aws_secretsmanager_secret.session_auth.arn

  tags = local.common_tags
}