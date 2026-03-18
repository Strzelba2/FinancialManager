
data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.project}-${local.env}-ecs-task-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn  = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_app" {
  name               = "${local.project}-${local.env}-ecs-task-app"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "traefik_ecs_discovery" {
  statement {
    sid    = "ECSDiscoveryRead"
    effect = "Allow"
    actions = [
      "ecs:ListClusters",
      "ecs:DescribeClusters",
      "ecs:ListServices",
      "ecs:DescribeServices",
      "ecs:ListTasks",
      "ecs:DescribeTasks",
      "ecs:DescribeTaskDefinition",
      "ecs:ListTaskDefinitions",
      "ecs:ListTagsForResource"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EC2DescribeRead"
    effect = "Allow"
    actions = [
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeNetworkInterfaces"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "traefik_task_role" {
  name               = "${local.project}-${local.env}-traefik-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.common_tags
}

resource "aws_iam_policy" "traefik_ecs_discovery" {
  name   = "${local.project}-${local.env}-traefik-ecs-discovery"
  policy = data.aws_iam_policy_document.traefik_ecs_discovery.json
}

resource "aws_iam_role_policy_attachment" "traefik_ecs_discovery_attach" {
  role      = aws_iam_role.traefik_task_role.name
  policy_arn = aws_iam_policy.traefik_ecs_discovery.arn
}