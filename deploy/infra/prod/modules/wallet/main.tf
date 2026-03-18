locals {
  name     = "fm-wallet"
  port     = 8001
  loggroup = "/financial-manager/prod/fm-wallet"

  wallet_host  = "wallet.${var.domain_name}"
  session_host = "session.${var.domain_name}"
  stock_host   = "stock.${var.domain_name}"

  auth_url  = "https://${local.session_host}/"
  stock_url = "https://${local.stock_host}/"

  redis_app_db = "redis://${var.redis_endpoint}:6379/1"
  redis_celery = "redis://${var.redis_endpoint}:6379/0"

  labels = {
    "traefik.enable" = "true"
    "traefik.http.routers.wallet.rule"        = "Host(`${local.wallet_host}`)"
    "traefik.http.routers.wallet.entrypoints" = "web"
    "traefik.http.routers.wallet.service"     = "wallet-svc"
    "traefik.http.services.wallet-svc.loadbalancer.server.port" = tostring(local.port)
  }
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

  desired_count = 1
  cpu           = "512"
  memory        = "1024"

  image          = var.image
  container_name = "wallet"
  container_port = local.port

  command = ["bash", "docker/fastapi/start.sh"]

  environment = {
    ENV_TYPE            = "prod"
    APP_HOST            = "0.0.0.0"
    APP_PORT            = tostring(local.port)

    UVICORN_WORKERS     = "2"
    UVICORN_LOG_LEVEL   = "info"
    UVICORN_PROXY_HEADERS = "true"

    POSTGRES_DB         = var.db_name
    POSTGRES_PORT       = "5432"

    REDIS_URL           = local.redis_app_db
    CELERY_BROKER_URL   = local.redis_celery
    CELERY_RESULT_BACKEND = local.redis_celery

    AUTH_URL            = local.auth_url
    STOCK_API_URL       = local.stock_url

    CPI_SYMBOL          = "CPIYPL.M"
    PROJECT_NAME        = "Financial Manager"
    PROJECT_DESCRIPTION = "Welcome to the Financial Manager"
    SITE_NAME           = "Financial Manager"
  }

  secrets = {
    POSTGRES_HOST     = "${var.rds_master_secret_arn}:host::"
    POSTGRES_USER     = "${var.rds_master_secret_arn}:username::"
    POSTGRES_PASSWORD = "${var.rds_master_secret_arn}:password::"
  }

  docker_labels = local.labels

  log_group_name     = local.loggroup
  log_retention_days = 14

  healthcheck_command = [
    "CMD-SHELL",
    "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2).read()\""
  ]

  tags = var.tags
}