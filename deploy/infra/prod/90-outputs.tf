output "ecr_repository_urls" {
  description = "Map repo_name -> repository_url"
  value       = module.ecr.repository_urls
}

output "ecr_repository_arns" {
  description = "Map repo_name -> repository_arn"
  value       = module.ecr.repository_arns
}

output "db_init_task_definition_arn" {
  value = var.enable_db_init_taskdef ? aws_ecs_task_definition.db_init[0].arn : null
}

output "rds_master_secret_arn" {
  value = var.enable_rds ? aws_secretsmanager_secret.rds_master[0].arn : null
}

output "rds_endpoint" {
  value = var.enable_rds ? aws_db_instance.pg[0].address : null
}