variable "aws_region" {
  type    = string
  default = "eu-central-1"
}

variable "domain" {
  type    = string
  default = "financialmanager.click"
}

variable "enable_redis" {
  type    = bool
  default = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "redis_db" {
  type    = number
  default = 1
}

variable "enable_niceui" {
  type    = bool
  default = true
}

variable "niceui_secret_key" {
  type      = string
  sensitive = true
}

variable "enable_nat_gateway" {
  type    = bool
  default = true
}

variable "nat_gateway_per_az" {
  type    = bool
  default = false
}

variable "enable_rds" {
  type    = bool
  default = false
}

variable "enable_db_init_taskdef" {
  type    = bool
  default = false
}

variable "enable_services" {
  type    = bool
  default = false
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_master_username" {
  type    = string
  default = "fmadmin"
}

variable "db_master_password" {
  type      = string
  sensitive = true
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = true
}

variable "db_names" {
  type = list(string)
  default = [
    "fm_session",
    "fm_wallet",
    "fm_stock",
  ]
}

variable "enable_pgadmin" {
  type    = bool
  default = false
}

variable "pgadmin_desired_count" {
  type    = number
  default = 1
}

variable "pgadmin_default_email" {
  type    = string
  default = "admin@example.com"
}

variable "pgadmin_default_password" {
  type      = string
  sensitive = true
}
