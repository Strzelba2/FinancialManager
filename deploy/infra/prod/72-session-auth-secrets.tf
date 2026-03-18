locals {
  session_auth_secret_name = "fm-${local.env}-session-auth"
}

variable "session_auth_django_secret_key" { 
    type = string
    sensitive = true 
    }
variable "session_auth_server_salt"{ 
    type = string
    sensitive = true 
    }
variable "session_auth_app_aes_key"{ 
    type = string
    sensitive = true 
    }
variable "session_auth_app_hmac_key"{ 
    type = string
    sensitive = true 
    }

variable "recaptcha_public_key"{ 
    type = string
    sensitive = true 
    }
variable "recaptcha_private_key" { 
    type = string
    sensitive = true 
    }

variable "ses_smtp_user" {
     type = string
     sensitive = true 
     }
variable "ses_smtp_pass"{ 
    type = string
    sensitive = true 
    }
variable "default_from_email"{ 
    type = string 
    }

variable "django_superuser_username"     { 
    type = string
    default = "admin" 
    }
variable "django_superuser_email" { 
    type = string
    default = "admin@example.com" 
    }
variable "django_superuser_password"{ 
    type = string
    sensitive = true 
    }
variable "django_superuser_first_name" { 
    type = string
    default = "Admin" 
    }
variable "django_superuser_last_name" { 
    type = string
    default = "User" 
    }

resource "aws_secretsmanager_secret" "session_auth" {
  name = local.session_auth_secret_name
  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "session_auth" {
  secret_id = aws_secretsmanager_secret.session_auth.id

  secret_string = jsonencode({
    django_secret_key     = var.session_auth_django_secret_key
    server_salt           = var.session_auth_server_salt
    app_aes_key           = var.session_auth_app_aes_key
    app_hmac_key          = var.session_auth_app_hmac_key

    recaptcha_public_key  = var.recaptcha_public_key
    recaptcha_private_key = var.recaptcha_private_key

    email_host            = "email-smtp.eu-central-1.amazonaws.com"
    email_port            = "587"
    email_user            = var.ses_smtp_user
    email_pass            = var.ses_smtp_pass
    default_from_email    = var.default_from_email

    su_username           = var.django_superuser_username
    su_email              = var.django_superuser_email
    su_password           = var.django_superuser_password
    su_first              = var.django_superuser_first_name
    su_last               = var.django_superuser_last_name
  })
}

output "session_auth_secret_arn" {
  value = aws_secretsmanager_secret.session_auth.arn
}