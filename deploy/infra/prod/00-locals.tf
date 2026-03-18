locals {
  project = "financial-manager"
  env     = "prod"

  domain_name  = var.domain
  public_hosts = toset(["ui", "wallet", "stock", "session", "pgadmin"])

  common_tags = {
    Project     = local.project
    Environment = local.env
    ManagedBy   = "Terraform"
  }
}