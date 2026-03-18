variable "enable" {
  type    = bool
  default = true
}

variable "name" { type = string }
variable "cluster_id" { type = string }

variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }

variable "subnets" { type = list(string) }
variable "security_group_ids" { type = list(string) }
variable "assign_public_ip" { 
    type = bool
    default = false 
    }

variable "desired_count" { 
    type = number
    default = 1 
    }
variable "cpu" { 
    type = string
    default = "256" 
    }
variable "memory" { 
    type = string
    default = "512" 
    }

variable "image" { type = string }
variable "container_name" { 
    type = string
    default = "app" 
    }
variable "container_port" { type = number }

variable "command" {
     type = list(string)
     default = null 
     }

variable "environment" { 
    type = map(string)
    default = {} 
    }
variable "secrets" {
  description = "Map ENV_NAME -> SecretsManager/SSM ARN"
  type        = map(string)
  default     = {}
}

variable "docker_labels" { 
    type = map(string)
    default = {} 
    }

variable "log_group_name" { type = string }
variable "log_retention_days" { 
    type = number
    default = 14 
    }

variable "healthcheck_command" { 
    type = list(string)
    default = null 
    }
variable "tags" { 
    type = map(string)
     default = {} 
     }

variable "create_log_group" {
  type    = bool
  default = false
}