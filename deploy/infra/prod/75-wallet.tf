locals {
  wallet_image = "${module.ecr.repository_urls["fm-wallet"]}:${var.image_tag}"
}

module "wallet" {
  source = "./modules/wallet"

  enable = var.enable_services
  domain_name = local.domain_name

  cluster_id         = aws_ecs_cluster.this.id
  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task_app.arn

  subnets            = module.network.private_app_subnet_ids
  security_group_ids = [module.network.sg_services_id]

  image          = local.wallet_image

  rds_master_secret_arn    = aws_secretsmanager_secret.rds_master[0].arn
  rds_endpoint   = aws_db_instance.pg[0].address
  redis_endpoint = aws_elasticache_replication_group.redis[0].primary_endpoint_address

  db_username = var.db_master_username
  db_password = var.db_master_password
  db_name     = "fm_wallet"

  tags = local.common_tags
}