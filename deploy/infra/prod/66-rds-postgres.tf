locals {
  rds_id          = "fm-${local.env}-pg"         
  rds_db_name     = "postgres"                   
  rds_secret_name = "fm-${local.env}-rds-master"  
}

resource "aws_db_subnet_group" "pg" {
  count      = var.enable_rds ? 1 : 0
  name       = "${local.rds_id}-subnets"
  subnet_ids = module.network.private_data_subnet_ids
  tags       = local.common_tags
}

resource "aws_db_instance" "pg" {
  count = var.enable_rds ? 1 : 0

  identifier = local.rds_id

  engine         = "postgres"
  engine_version = "16.10"
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage_gb
  storage_type      = "gp3"

  db_name  = local.rds_db_name
  username = var.db_master_username
  password = var.db_master_password

  port = 5432

  multi_az            = var.db_multi_az
  publicly_accessible = false

  db_subnet_group_name   = aws_db_subnet_group.pg[0].name
  vpc_security_group_ids = [module.network.sg_data_id]

  deletion_protection = var.db_deletion_protection
  skip_final_snapshot = var.db_skip_final_snapshot

  tags = local.common_tags
}

resource "aws_secretsmanager_secret" "rds_master" {
  count = var.enable_rds ? 1 : 0
  name  = local.rds_secret_name
  tags  = local.common_tags
}

resource "aws_secretsmanager_secret_version" "rds_master" {
  count     = var.enable_rds ? 1 : 0
  secret_id = aws_secretsmanager_secret.rds_master[0].id

  secret_string = jsonencode({
    host     = aws_db_instance.pg[0].address
    port     = aws_db_instance.pg[0].port
    username = var.db_master_username
    password = var.db_master_password
  })
}