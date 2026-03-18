locals {
  db_init_family     = "fm-${local.env}-db-init"
  db_init_log_group  = "/${local.project}/${local.env}/fm-db-init"
  db_init_enabled    = var.enable_db_init_taskdef && var.enable_rds
  db_init_script = <<-EOT
    set -euo pipefail

    echo "DB init starting... version=2026-03-12-v4"
    echo "Host=$PGHOST Port=$PGPORT User=$PGUSER"

    wait_for_db() {
      until psql \
        -h "$PGHOST" \
        -p "$PGPORT" \
        -U "$PGUSER" \
        -d postgres \
        -v ON_ERROR_STOP=1 \
        -Atqc "SELECT 1" >/dev/null 2>&1; do
        echo "PostgreSQL not ready yet, sleeping..."
        sleep 2
      done
    }

    create_db() {
      DB="$1"
      echo "Ensuring database exists: $DB"

      EXISTS=$(
        psql \
          -h "$PGHOST" \
          -p "$PGPORT" \
          -U "$PGUSER" \
          -d postgres \
          -v ON_ERROR_STOP=1 \
          -Atqc "SELECT 1 FROM pg_database WHERE datname = '$DB';"
      )

      if [ "$EXISTS" = "1" ]; then
        echo "DB exists: $DB"
      else
        echo "Creating DB: $DB"
        psql \
          -h "$PGHOST" \
          -p "$PGPORT" \
          -U "$PGUSER" \
          -d postgres \
          -v ON_ERROR_STOP=1 \
          -c "CREATE DATABASE \"$DB\""
        echo "DB created: $DB"
      fi
    }

    wait_for_db

    create_db "fm_session"
    create_db "fm_wallet"
    create_db "fm_stock"

    echo "DB init done."
    psql \
      -h "$PGHOST" \
      -p "$PGPORT" \
      -U "$PGUSER" \
      -d postgres \
      -c "\\l" | grep fm_ || true
  EOT
}

resource "aws_cloudwatch_log_group" "db_init" {
  count             = local.db_init_enabled ? 1 : 0
  name              = local.db_init_log_group
  retention_in_days = 7
  tags              = local.common_tags
}

data "aws_iam_policy_document" "db_init_secret_read" {
  count = local.db_init_enabled ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [aws_secretsmanager_secret.rds_master[0].arn]
  }
}

resource "aws_iam_policy" "db_init_secret_read" {
  count  = local.db_init_enabled ? 1 : 0
  name   = "fm-${local.env}-db-init-secret-read"
  policy = data.aws_iam_policy_document.db_init_secret_read[0].json
}

resource "aws_iam_role_policy_attachment" "db_init_secret_read_attach" {
  count      = local.db_init_enabled ? 1 : 0
  role       = aws_iam_role.ecs_task_app.name
  policy_arn = aws_iam_policy.db_init_secret_read[0].arn
}

resource "aws_ecs_task_definition" "db_init" {
  count                    = local.db_init_enabled ? 1 : 0
  family                   = local.db_init_family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task_app.arn

  container_definitions = jsonencode([
    {
      name       = "db-init"
      image      = "postgres:16-alpine"
      essential  = true
      entryPoint = ["sh", "-lc"]
      command    = [local.db_init_script]

      secrets = [
        { name = "PGHOST",     valueFrom = "${aws_secretsmanager_secret.rds_master[0].arn}:host::" },
        { name = "PGPORT",     valueFrom = "${aws_secretsmanager_secret.rds_master[0].arn}:port::" },
        { name = "PGUSER",     valueFrom = "${aws_secretsmanager_secret.rds_master[0].arn}:username::" },
        { name = "PGPASSWORD", valueFrom = "${aws_secretsmanager_secret.rds_master[0].arn}:password::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = local.db_init_log_group
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  depends_on = [aws_db_instance.pg]
  tags       = local.common_tags
}