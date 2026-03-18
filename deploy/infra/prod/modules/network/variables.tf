variable "name_prefix" { type = string }

variable "vpc_cidr" { type = string }

variable "azs" {
  type        = list(string)
  description = "List of AZ names to use (e.g., [\"eu-central-1a\", \"eu-central-1b\"])"
}

variable "public_subnet_cidrs" {
  type = list(string)
}

variable "private_app_subnet_cidrs" {
  type = list(string)
}

variable "private_data_subnet_cidrs" {
  type = list(string)
}

variable "enable_nat_gateway" {
  type    = bool
  default = true
}

variable "nat_gateway_per_az" {
  type    = bool
  default = false
}

variable "service_ports" {
  type        = list(number)
  description = "Ports for internal HTTP services behind Traefik (e.g. 8000/8001/8501)."
  default     = [8000, 8001, 8501]
}

variable "tags" {
  type    = map(string)
  default = {}
}