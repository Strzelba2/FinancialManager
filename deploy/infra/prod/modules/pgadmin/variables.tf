variable "enable" { type = bool }

variable "domain_name" { type = string }

variable "cluster_id" { type = string }
variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }

variable "subnets" { type = list(string) }
variable "security_group_ids" { type = list(string) }

variable "image" { type = string }

variable "rds_master_secret_arn" { type = string }

variable "pgadmin_default_email" { type = string }
variable "pgadmin_default_password" {
  type      = string
  sensitive = true
}

variable "desired_count" { type = number }

variable "tags" {
  type    = map(string)
  default = {}
}