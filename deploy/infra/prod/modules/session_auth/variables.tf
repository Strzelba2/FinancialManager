variable "enable" { 
    type = bool
    default = true 
    }
variable "enable_celery" {
    type = bool
    default = true 
    }
variable "bootstrap_superuser" { 
    type = bool
    default = false 
    }

variable "cluster_id" { 
    type = string 
    }
variable "execution_role_arn" { 
    type = string 
    }
variable "task_role_arn" { 
    type = string 
    }
variable "subnets" { 
    type = list(string) 
    }
variable "security_group_ids" { 
    type = list(string) 
    }

variable "image" { 
    type = string 
    }
variable "domain_name" { 
    type = string 
    }

variable "rds_master_secret_arn" { 
    type = string 
    }
variable "redis_endpoint" { 
    type = string 
    }
variable "session_auth_secret_arn" { 
    type = string 
    }

variable "tags" { 
    type = map(string)
    default = {} 
    }