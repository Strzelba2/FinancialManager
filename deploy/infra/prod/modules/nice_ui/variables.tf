variable "enable" {
  type    = bool
  default = true
}

variable "cluster_id" { type = string }
variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }
variable "subnets" { type = list(string) }
variable "security_group_ids" { type = list(string) }

variable "image" { type = string } 
variable "domain_name" { type = string }

variable "secret_key" { 
    type = string
    sensitive = true 
    }

variable "enable_redis" { 
    type = bool
    default = true 
    }
    
variable "redis_endpoint" { 
    type = string
    default = null 
    } 

variable "redis_db" { 
    type = number
    default = 1 
    }

variable "tags" { 
    type = map(string)
    default = {} 
    }