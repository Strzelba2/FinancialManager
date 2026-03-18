data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "ecs_exec_read_secrets" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]

    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:fm-${local.env}-*"
    ]
  }
}

resource "aws_iam_policy" "ecs_exec_read_secrets" {
  name   = "${local.project}-${local.env}-ecs-exec-read-secrets"
  policy = data.aws_iam_policy_document.ecs_exec_read_secrets.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_exec_read_secrets_attach" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn  = aws_iam_policy.ecs_exec_read_secrets.arn
}