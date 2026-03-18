locals {
  traefik_name      = "fm-traefik"
  traefik_image     = "docker.io/traefik:v3.6.5"
  traefik_log_group = "/${local.project}/${local.env}/fm-traefik"
}

resource "aws_ecs_task_definition" "traefik" {
  family                   = "${local.project}-${local.env}-traefik"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"

  cpu    = "256"
  memory = "512"

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.traefik_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "traefik"
      image     = local.traefik_image
      essential = true

      portMappings = [
        { containerPort = 80, hostPort = 80, protocol = "tcp" }
      ]

      environment = [
        { name = "AWS_REGION", value = data.aws_region.current.name },
        { name = "ECS_CLUSTER", value = aws_ecs_cluster.this.name }
      ]

      command = [
        "--log.level=INFO",
        "--accesslog=true",
        "--api.dashboard=false",

        "--entrypoints.web.address=:80",
        "--entrypoints.web.forwardedheaders.trustedips=10.20.0.0/16",
        "--ping=true",
        "--ping.entrypoint=web",

        "--providers.ecs=true",
        "--providers.ecs.region=${data.aws_region.current.name}",
        "--providers.ecs.clusters=${aws_ecs_cluster.this.name}",
        "--providers.ecs.exposedByDefault=false",

        "--providers.ecs.autoDiscoverClusters=true",

        "--providers.ecs.exposedByDefault=false"
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "wget -qO- http://127.0.0.1:80/ping || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = local.traefik_log_group
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_service" "traefik" {
  name            = local.traefik_name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.traefik.arn
  desired_count   = 1

  launch_type = "FARGATE"

  network_configuration {
    subnets         = module.network.private_app_subnet_ids
    security_groups = [module.network.sg_traefik_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.traefik.arn
    container_name   = "traefik"
    container_port   = 80
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = local.common_tags
}