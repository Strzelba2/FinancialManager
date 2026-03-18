variable "repositories" {
  description = "Map of ECR repos. Key = repo name. Value can override defaults."
  type = map(object({
    image_tag_mutability = optional(string) 
    scan_on_push         = optional(bool)
    force_delete         = optional(bool)
    encryption_type      = optional(string) 
    kms_key_arn          = optional(string)

    lifecycle_policy_json = optional(string)

    repository_policy_json = optional(string)
  }))
}

variable "default_image_tag_mutability" {
  type        = string
  default     = "MUTABLE"
  description = "Default tag mutability for repositories."
}

variable "default_scan_on_push" {
  type        = bool
  default     = true
  description = "Enable ECR image scan on push."
}

variable "default_force_delete" {
  type        = bool
  default     = false
  description = "If true, terraform destroy can delete repos with images."
}

variable "default_encryption_type" {
  type        = string
  default     = "AES256"
  description = "AES256 or KMS."
}

variable "default_kms_key_arn" {
  type        = string
  default     = null
  description = "KMS key ARN if encryption_type is KMS."
}

variable "untagged_expire_days" {
  type        = number
  default     = 7
  description = "Expire untagged images older than this many days."
}

variable "keep_last_images" {
  type        = number
  default     = 50
  description = "Keep last N images (tagged+untagged)."
}

variable "enable_repository_policy" {
  type        = bool
  default     = false
  description = "If true, attach an ECR repository policy (resource-based). Usually not needed in same AWS account."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags applied to ECR resources."
}