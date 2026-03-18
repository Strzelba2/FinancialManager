output "repository_arns" {
  description = "Map repo_name -> repository_arn"
  value       = { for k, r in aws_ecr_repository.this : k => r.arn }
}

output "repository_urls" {
  description = "Map repo_name -> repository_url"
  value       = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}