locals {
  ecs_cluster_name = "${local.project}-${local.env}-cluster"


  ecs_log_groups = [
    "fm-traefik",
    "fm-wallet",
    "fm-stock",
    "fm-session-auth",
    "fm-nice-ui",
  ]

  log_retention_days = 14
}

resource "aws_ecs_cluster" "this" {
  name = local.ecs_cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

resource "aws_cloudwatch_log_group" "ecs" {
  for_each = toset(local.ecs_log_groups)

  name              = "/${local.project}/${local.env}/${each.value}"
  retention_in_days = local.log_retention_days

  tags = local.common_tags
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_app_role_arn" {
  value = aws_iam_role.ecs_task_app.arn
}

output "traefik_task_role_arn" {
  value = aws_iam_role.traefik_task_role.arn
}