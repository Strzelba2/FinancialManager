locals {
  pgadmin_image = "${module.ecr.repository_urls["fm-pgadmin"]}:${var.image_tag}"
}

module "pgadmin" {
  source = "./modules/pgadmin"

  enable      = var.enable_pgadmin
  domain_name = local.domain_name

  cluster_id         = aws_ecs_cluster.this.id
  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task_app.arn

  subnets            = module.network.private_app_subnet_ids
  security_group_ids = [module.network.sg_services_id]

  image = local.pgadmin_image

  rds_master_secret_arn = aws_secretsmanager_secret.rds_master[0].arn

  pgadmin_default_email    = var.pgadmin_default_email
  pgadmin_default_password = var.pgadmin_default_password
  desired_count            = var.pgadmin_desired_count

  tags = local.common_tags
}