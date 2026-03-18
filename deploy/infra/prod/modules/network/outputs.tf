output "vpc_id" { value = aws_vpc.this.id }

output "public_subnet_ids" {
  value = [for s in aws_subnet.public : s.id]
}

output "private_app_subnet_ids" {
  value = [for s in aws_subnet.private_app : s.id]
}

output "private_data_subnet_ids" {
  value = [for s in aws_subnet.private_data : s.id]
}

output "sg_alb_id"      { value = aws_security_group.alb.id }
output "sg_traefik_id"  { value = aws_security_group.traefik.id }
output "sg_services_id" { value = aws_security_group.services.id }
output "sg_data_id"     { value = aws_security_group.data.id }