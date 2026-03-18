data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "network" {
  source = "./modules/network"

  name_prefix = "${local.project}-${local.env}" 

  vpc_cidr = "10.20.0.0/16"
  azs      = local.azs

  public_subnet_cidrs = [
    "10.20.0.0/24",
    "10.20.1.0/24",
  ]

  private_app_subnet_cidrs = [
    "10.20.10.0/24",
    "10.20.11.0/24",
  ]

  private_data_subnet_cidrs = [
    "10.20.20.0/24",
    "10.20.21.0/24",
  ]

  enable_nat_gateway   = var.enable_nat_gateway
  nat_gateway_per_az   = var.nat_gateway_per_az

  service_ports = [80, 8000, 8001, 8501]

  tags = local.common_tags
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_app_subnet_ids" {
  value = module.network.private_app_subnet_ids
}

output "private_data_subnet_ids" {
  value = module.network.private_data_subnet_ids
}

output "sg_alb_id" {
  value = module.network.sg_alb_id
}

output "sg_traefik_id" {
  value = module.network.sg_traefik_id
}

output "sg_services_id" {
  value = module.network.sg_services_id
}

output "sg_data_id" {
  value = module.network.sg_data_id
}