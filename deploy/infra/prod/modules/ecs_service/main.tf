data "aws_region" "current" {}

locals {
  env_list = [
    for k, v in var.environment : {
      name  = k
      value = tostring(v)
    }
  ]

  secrets_list = [
    for k, arn in var.secrets : {
      name      = k
      valueFrom = arn
    }
  ]

  port_mappings = var.container_port == null ? null : [
    {
      containerPort = var.container_port
      hostPort      = var.container_port
      protocol      = "tcp"
    }
  ]

  container = merge(
    {
      name      = var.container_name
      image     = var.image
      essential = true

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = var.log_group_name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
    },
    local.port_mappings != null ? {
      portMappings = local.port_mappings
    } : {},
    var.command != null ? {
      command = var.command
    } : {},
    length(local.env_list) > 0 ? {
      environment = local.env_list
    } : {},
    length(local.secrets_list) > 0 ? {
      secrets = local.secrets_list
    } : {},
    length(var.docker_labels) > 0 ? {
      dockerLabels = var.docker_labels
    } : {},
    var.healthcheck_command != null ? {
      healthCheck = {
        command     = var.healthcheck_command
        interval    = 30
        timeout     = 5
        retries     = 5
        startPeriod = 90
      }
    } : {}
  )
}

resource "aws_cloudwatch_log_group" "this" {
  count = (var.enable && var.create_log_group) ? 1 : 0

  name              = var.log_group_name
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_ecs_task_definition" "this" {
  count = var.enable ? 1 : 0

  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory

  execution_role_arn = var.execution_role_arn
  task_role_arn      = var.task_role_arn

  container_definitions = jsonencode([local.container])

  tags = var.tags
}

resource "aws_ecs_service" "this" {
  count = var.enable ? 1 : 0

  name            = var.name
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.this[0].arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnets
    security_groups  = var.security_group_ids
    assign_public_ip = var.assign_public_ip
  }

  tags = var.tags
}