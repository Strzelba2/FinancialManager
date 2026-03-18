locals {
  session_host = "session.${var.domain_name}"
  wallet_host  = "wallet.${var.domain_name}"
  ui_host      = "ui.${var.domain_name}"

  redis_sessions = "redis://${var.redis_endpoint}:6379/1"
  celery_broker  = "redis://${var.redis_endpoint}:6379/0"
  celery_backend = "redis://${var.redis_endpoint}:6379/0"

  env_common = {
    ENV_TYPE     = "prod"
    APP_PROTOCOL = "https"

    SESSION_DOMAIN = local.session_host
    WALLET_DOMAIN  = local.wallet_host
    UI_DOMAIN      = local.ui_host

    POSTGRES_DB   = "fm_session"
    POSTGRES_PORT = "5432"

    REDIS_URL             = local.redis_sessions
    CELERY_BROKER_URL     = local.celery_broker
    CELERY_RESULT_BACKEND = local.celery_backend

    EMAIL_DOMAIN_ALLOWED_LIST = "localhost,gmail.com,wp.pl"

    ADMIN_PATH = "admin/"
    ADMIN_FAILURE_LIMIT = "3"
    ADMIN_TEMPORARY_BLOCK_TIME = "3600"
    USER_TEMPORARY_BLOCK_TIME  = "3600"

    ADMIN_ALLOWED_IPS   = "['127.0.0.1','10.20.0.0/16','79.184.255.203']"
    ALLOWED_WALLET_IPS  = "['10.20.0.0/16']"

    VALID_HMAC = "3600"

    DJANGO_COLLECTSTATIC = "0"
    DJANGO_CREATE_SUPERUSER = var.bootstrap_superuser ? "1" : "0"
    DJANGO_SUPERUSER_USERNAME = "admin"
    DJANGO_SUPERUSER_EMAIL    = "admin@example.com"
    DJANGO_SUPERUSER_FIRST_NAME = "Admin"
    DJANGO_SUPERUSER_LAST_NAME  = "User"

    ALLOWED_HOSTS = "${local.session_host},ui.${var.domain_name},${local.wallet_host},localhost,127.0.0.1"

    CELERY_LOG_LEVEL   = "INFO"
    CELERY_CONCURRENCY = "2"
    CELERY_POOL        = "prefork"
  }

  secrets_common = {
    POSTGRES_HOST     = "${var.rds_master_secret_arn}:host::"
    POSTGRES_USER     = "${var.rds_master_secret_arn}:username::"
    POSTGRES_PASSWORD = "${var.rds_master_secret_arn}:password::"

    SECRET_KEY            = "${var.session_auth_secret_arn}:django_secret_key::"
    SERVER_SALT           = "${var.session_auth_secret_arn}:server_salt::"
    APP_AES_KEY           = "${var.session_auth_secret_arn}:app_aes_key::"
    APP_HMAC_KEY          = "${var.session_auth_secret_arn}:app_hmac_key::"
    RECAPTCHA_PUBLIC_KEY  = "${var.session_auth_secret_arn}:recaptcha_public_key::"
    RECAPTCHA_PRIVATE_KEY = "${var.session_auth_secret_arn}:recaptcha_private_key::"

    EMAIL_HOST          = "${var.session_auth_secret_arn}:email_host::"
    EMAIL_PORT          = "${var.session_auth_secret_arn}:email_port::"
    EMAIL_HOST_USER     = "${var.session_auth_secret_arn}:email_user::"
    EMAIL_HOST_PASSWORD = "${var.session_auth_secret_arn}:email_pass::"
    DEFAULT_FROM_EMAIL  = "${var.session_auth_secret_arn}:default_from_email::"

    DJANGO_SUPERUSER_PASSWORD = "${var.session_auth_secret_arn}:su_password::"
  }

  traefik_labels = {
    "traefik.enable" = "true"
    "traefik.http.routers.session.rule" = "Host(`session.${var.domain_name}`) && (PathPrefix(`/admin`) || PathPrefix(`/register`) || PathPrefix(`/activate`) || PathPrefix(`/login`) || PathPrefix(`/logout`) || PathPrefix(`/finalize-login`) || PathPrefix(`/verifySession`) || PathPrefix(`/static`) || PathPrefix(`/media`) || PathPrefix(`/.well-known`) || Path(`/healthz`))"
    "traefik.http.routers.session.entrypoints" = "web"
    "traefik.http.routers.session.service"     = "session-svc"
    "traefik.http.services.session-svc.loadbalancer.server.port" = "8000"
  }
}

module "web" {
  source = "../ecs_service"

  enable             = var.enable
  name               = "fm-session-auth"
  cluster_id         = var.cluster_id
  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

  subnets            = var.subnets
  security_group_ids = var.security_group_ids

  desired_count = 1
  cpu           = "512"
  memory        = "1024"

  image          = var.image
  container_name = "session-auth"
  container_port = 8000

  command = ["bash", "docker/session/start.sh"]

  environment   = local.env_common
  secrets       = local.secrets_common
  docker_labels = local.traefik_labels

  log_group_name       = "/financial-manager/prod/fm-session-auth"
  log_retention_days   = 14

  healthcheck_command      = ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()\""]


  tags = var.tags
}

module "worker" {
  source = "../ecs_service"

  enable             = var.enable && var.enable_celery
  name               = "fm-session-auth-worker"
  cluster_id         = var.cluster_id
  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

  subnets            = var.subnets
  security_group_ids = var.security_group_ids

  desired_count = 1
  cpu           = "512"
  memory        = "1024"

  image          = var.image
  container_name = "celery-worker"
  container_port = null

  command = ["bash", "docker/celery/worker/start.sh"]

  environment = local.env_common
  secrets     = local.secrets_common

  log_group_name       = "/financial-manager/prod/fm-session-auth-worker"
  log_retention_days   = 14

  tags = var.tags

  depends_on = [module.web] 
}

module "beat" {
  source = "../ecs_service"

  enable             = var.enable && var.enable_celery
  name               = "fm-session-auth-beat"
  cluster_id         = var.cluster_id
  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

  subnets            = var.subnets
  security_group_ids = var.security_group_ids

  desired_count = 1
  cpu           = "256"
  memory        = "512"

  image          = var.image
  container_name = "celery-beat"
  container_port = null

  command = ["bash", "docker/celery/beat/start.sh"]

  environment = local.env_common
  secrets     = local.secrets_common

  log_group_name       = "/financial-manager/prod/fm-session-auth-beat"
  log_retention_days   = 14

  tags = var.tags

  depends_on = [module.web]
}