resource "aws_cloudwatch_log_group" "ecs_session_extra" {
  for_each = toset([
    "fm-session-auth-worker",
    "fm-session-auth-beat",
  ])

  name              = "/${local.project}/${local.env}/${each.value}"
  retention_in_days = 14
  tags              = local.common_tags
}