locals {
  name = "fm-stock"
  port = 8001

  host = "stock.${var.domain_name}"

  env = {
    ENV_TYPE    = "prod"
    APP_HOST    = "0.0.0.0"
    APP_PORT    = tostring(local.port)

    POSTGRES_DB   = "fm_stock"
    POSTGRES_PORT = "5432"

    REDIS_URL            = "redis://${var.redis_endpoint}:6379/1"
    CELERY_BROKER_URL    = "redis://${var.redis_endpoint}:6379/0"   
    CELERY_RESULT_BACKEND= "redis://${var.redis_endpoint}:6379/0"

    ST_BASE_URL                  = "https://stooq.pl"
    ST_START_WSE_QUOTE_URL       = "https://stooq.pl/t/?i=513&v=0"
    ST_START_NC_QUOTE_URL        = "https://stooq.pl/t/?i=514&v=0"
    ST_START_COMMODITIES_QUOTE_URL = "https://stooq.pl/t/?i=512&v=0"
    ST_START_CPI_QUOTE_URL       = "https://stooq.pl/t/?i=539&v=0"

    GPW_BASE_URL = "https://gpw.pl/"
    GPW_PATH     = "ajaxindex.php?action=GPWQuotations&start=showTable&tab=all&lang=EN&type=&full=1&format=html&download_xls=1"
    NC_BASE_URL  = "https://newconnect.pl/"
    NC_PATH      = "ajaxindex.php?action=NCExternalDataFrontController&start=showTable&type=ALL&system_type=&tab=all&lang=EN&full=1&format=html&download_xls=1"

  }

  secrets = {
    POSTGRES_HOST     = "${var.rds_master_secret_arn}:host::"
    POSTGRES_USER     = "${var.rds_master_secret_arn}:username::"
    POSTGRES_PASSWORD = "${var.rds_master_secret_arn}:password::"
  }

  labels = {
    "traefik.enable" = "true"

    "traefik.http.routers.stock.rule"        = "Host(`stock.${var.domain_name}`)"
    "traefik.http.routers.stock.entrypoints" = "web"
    "traefik.http.routers.stock.service"     = "stock-svc"

    "traefik.http.services.stock-svc.loadbalancer.server.port" = tostring(local.port)
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
  assign_public_ip   = false

  desired_count = 1         
  cpu           = "512"
  memory        = "1024"

  image          = var.image
  container_name = "stock"
  container_port = local.port

  command = ["bash", "docker/fastapi/start.sh"]

  environment   = local.env
  secrets       = local.secrets
  docker_labels = local.labels

  log_group_name     = "/financial-manager/prod/fm-stock"
  log_retention_days = 14

  healthcheck_command = [
    "CMD-SHELL",
    "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2).read()\""
  ]

  tags = var.tags
}