locals {
  name     = "fm-pgadmin"
  host     = "pgadmin.${var.domain_name}"
  port     = 80
  loggroup = "/financial-manager/prod/fm-pgadmin"

  labels = {
    "traefik.enable" = "true"
    "traefik.http.routers.pgadmin.rule"        = "Host(`pgadmin.${var.domain_name}`)"
    "traefik.http.routers.pgadmin.entrypoints" = "web"
    "traefik.http.routers.pgadmin.service"     = "pgadmin-svc"
    "traefik.http.services.pgadmin-svc.loadbalancer.server.port" = "80"
  }
}

resource "aws_secretsmanager_secret" "pgadmin_admin" {
  count = var.enable ? 1 : 0
  name  = "fm-prod-pgadmin-admin"
  tags  = var.tags
}

resource "aws_secretsmanager_secret_version" "pgadmin_admin" {
  count         = var.enable ? 1 : 0
  secret_id     = aws_secretsmanager_secret.pgadmin_admin[0].id
  secret_string = var.pgadmin_default_password
}

module "svc" {
  source = "../ecs_service"

  enable             = var.enable
  name               = local.name
  cluster_id         = var.cluster_id
  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

  subnets            = var.subnets
  security_group_ids = var.security_group_ids

  assign_public_ip = false
  desired_count    = var.desired_count
  cpu              = "256"
  memory           = "512"

  image          = var.image
  container_name = "pgadmin"
  container_port = local.port

  environment = {
    PGADMIN_DEFAULT_EMAIL   = var.pgadmin_default_email
    PGADMIN_LISTEN_PORT     = "80"
    PGADMIN_DISABLE_POSTFIX = "1"
    PGADMIN_CONFIG_ENHANCED_COOKIE_PROTECTION = "True"
  }

  secrets = {
    PGADMIN_DEFAULT_PASSWORD = aws_secretsmanager_secret.pgadmin_admin[0].arn

    RDS_HOST     = "${var.rds_master_secret_arn}:host::"
    RDS_PORT     = "${var.rds_master_secret_arn}:port::"
    RDS_USER     = "${var.rds_master_secret_arn}:username::"
    RDS_PASSWORD = "${var.rds_master_secret_arn}:password::"
  }

  docker_labels = local.labels

  log_group_name      = local.loggroup
  log_retention_days  = 7
  create_log_group    = true

  healthcheck_command = ["CMD-SHELL", "wget -qO- http://127.0.0.1:80/misc/ping >/dev/null || exit 1"]

  tags = var.tags
}