locals {
  name     = "fm-nice-ui"
  port     = 8501
  loggroup = "/financial-manager/prod/fm-nice-ui"

  redis_url = (
    var.enable_redis
    ? "redis://${var.redis_endpoint}:6379/${var.redis_db}"
    : null
  )

  wallet_api_url = "https://wallet.${var.domain_name}/"
  stock_api_url  = "https://stock.${var.domain_name}/"
  auth_api_url   = "https://session.${var.domain_name}/"
  ui_api_url    = "https://ui.${var.domain_name}/"

  labels = {
    "traefik.enable" = "true"

    "traefik.http.services.ui-service.loadbalancer.server.port" = tostring(local.port)
    "traefik.http.middlewares.nocache.headers.customResponseHeaders.Cache-Control" = "no-store"

    "traefik.http.middlewares.ui-forwardauth.forwardauth.address" = "https://session.${var.domain_name}/verifySession/"
    "traefik.http.middlewares.ui-forwardauth.forwardauth.trustForwardHeader" = "true"
    "traefik.http.middlewares.ui-forwardauth.forwardauth.authResponseHeaders" = "X-User"
    "traefik.http.middlewares.ui-forwardauth.forwardauth.addAuthCookiesToResponse" = "hmac,sessionid"

    "traefik.http.routers.ui-root.rule" = "Host(`ui.${var.domain_name}`) && Path(`/`)"
    "traefik.http.routers.ui-root.entrypoints" = "web"
    "traefik.http.routers.ui-root.service" = "ui-service"
    "traefik.http.routers.ui-root.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-root.priority" = "200"

    "traefik.http.routers.ui-static.rule" = "Host(`ui.${var.domain_name}`) && (PathPrefix(`/_nicegui`) || PathPrefix(`/_nicegui_ws`) || Path(`/favicon.png`) || PathPrefix(`/.well-known`) || Path(`/healthz`))"
    "traefik.http.routers.ui-static.entrypoints" = "web"
    "traefik.http.routers.ui-static.service" = "ui-service"
    "traefik.http.routers.ui-static.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-static.priority" = "200"

    "traefik.http.routers.ui-home.rule" = "Host(`ui.${var.domain_name}`) && PathPrefix(`/home`)"
    "traefik.http.routers.ui-home.entrypoints" = "web"
    "traefik.http.routers.ui-home.service" = "ui-service"
    "traefik.http.routers.ui-home.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-home.priority" = "200"

    "traefik.http.routers.ui-login.rule" = "Host(`ui.${var.domain_name}`) && PathPrefix(`/login`)"
    "traefik.http.routers.ui-login.entrypoints" = "web"
    "traefik.http.routers.ui-login.service" = "ui-service"
    "traefik.http.routers.ui-login.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-login.priority" = "200"

    "traefik.http.routers.ui-login-fin.rule" = "Host(`ui.${var.domain_name}`) && PathPrefix(`/finalize-login`)"
    "traefik.http.routers.ui-login-fin.entrypoints" = "web"
    "traefik.http.routers.ui-login-fin.service" = "ui-service"
    "traefik.http.routers.ui-login-fin.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-login-fin.priority" = "200"

    "traefik.http.routers.ui-register.rule" = "Host(`ui.${var.domain_name}`) && PathPrefix(`/register`)"
    "traefik.http.routers.ui-register.entrypoints" = "web"
    "traefik.http.routers.ui-register.service" = "ui-service"
    "traefik.http.routers.ui-register.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-register.priority" = "200"

    "traefik.http.routers.ui-error.rule" = "Host(`ui.${var.domain_name}`) && PathPrefix(`/error`)"
    "traefik.http.routers.ui-error.entrypoints" = "web"
    "traefik.http.routers.ui-error.service" = "ui-service"
    "traefik.http.routers.ui-error.middlewares" = "nocache@ecs"
    "traefik.http.routers.ui-error.priority" = "200"


    "traefik.http.routers.ui-protected.rule" = "Host(`ui.${var.domain_name}`) && PathPrefix(`/`)"
    "traefik.http.routers.ui-protected.entrypoints" = "web"
    "traefik.http.routers.ui-protected.service" = "ui-service"
    "traefik.http.routers.ui-protected.middlewares" = "ui-forwardauth@ecs,nocache@ecs"
    "traefik.http.routers.ui-protected.priority" = "1"
  }
}

locals {
  redis_ok = (!var.enable) || (var.enable && var.enable_redis && var.redis_endpoint != null)
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
  cpu           = "256"
  memory        = "512"

  image          = var.image
  container_name = "nice-ui"
  container_port = local.port

  command = ["python3", "main.py"]

  environment = {
    ENV_TYPE          = "prod"
    APP_HOST          = "0.0.0.0"
    APP_PORT          = tostring(local.port)

    SECRET_KEY        = var.secret_key
    NICEGUI_REDIS_URL = local.redis_url

    WALLET_API_URL    = local.wallet_api_url
    STOCK_API_URL     = local.stock_api_url
    AUTH_URL          = local.auth_api_url
    UI_API_URL       = local.ui_api_url
  }

  docker_labels = local.labels

  log_group_name       = local.loggroup
  log_retention_days   = 14
  healthcheck_command = [
    "CMD-SHELL",
    "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/healthz', timeout=2).read()\""
  ]

  tags = var.tags
}

resource "null_resource" "preconditions" {
  count = var.enable ? 1 : 0

  lifecycle {
    precondition {
      condition     = local.redis_ok
      error_message = "NiceUI requires Redis. Set enable_redis=true and provide redis_endpoint, or set enable=false."
    }
  }
}