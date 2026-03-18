resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags = merge(var.tags, {
    Name = "${var.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  for_each = {
    for i, az in var.azs : az => {
      cidr = var.public_subnet_cidrs[i]
      az   = az
    }
  }

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-public-${each.key}"
    Tier = "public"
  })
}

resource "aws_subnet" "private_app" {
  for_each = {
    for i, az in var.azs : az => {
      cidr = var.private_app_subnet_cidrs[i]
      az   = az
    }
  }

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-private-app-${each.key}"
    Tier = "private-app"
  })
}

resource "aws_subnet" "private_data" {
  for_each = {
    for i, az in var.azs : az => {
      cidr = var.private_data_subnet_cidrs[i]
      az   = az
    }
  }

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-private-data-${each.key}"
    Tier = "private-data"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-rt-public" })
}

resource "aws_route" "public_igw" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count = var.enable_nat_gateway ? (var.nat_gateway_per_az ? length(var.azs) : 1) : 0
  domain = "vpc"
  tags = merge(var.tags, { Name = "${var.name_prefix}-nat-eip-${count.index}" })
}

resource "aws_nat_gateway" "this" {
  count = var.enable_nat_gateway ? (var.nat_gateway_per_az ? length(var.azs) : 1) : 0

  allocation_id = aws_eip.nat[count.index].id

  subnet_id = (
    var.nat_gateway_per_az
    ? values(aws_subnet.public)[count.index].id
    : values(aws_subnet.public)[0].id
  )

  tags = merge(var.tags, { Name = "${var.name_prefix}-nat-${count.index}" })
}

resource "aws_route_table" "private_app" {
  for_each = aws_subnet.private_app
  vpc_id = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-rt-private-app-${each.key}" })
}

resource "aws_route" "private_app_nat" {
  for_each = var.enable_nat_gateway ? aws_route_table.private_app : {}

  route_table_id         = each.value.id
  destination_cidr_block = "0.0.0.0/0"

  nat_gateway_id = (
    var.nat_gateway_per_az
    ? aws_nat_gateway.this[index(var.azs, each.key)].id
    : aws_nat_gateway.this[0].id
  )
}

resource "aws_route_table_association" "private_app" {
  for_each = aws_subnet.private_app
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_app[each.key].id
}

resource "aws_route_table" "private_data" {
  vpc_id = aws_vpc.this.id
  tags = merge(var.tags, { Name = "${var.name_prefix}-rt-private-data" })
}

resource "aws_route_table_association" "private_data" {
  for_each = aws_subnet.private_data
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_data.id
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-sg-alb"
  description = "ALB SG: HTTPS from internet, forward to Traefik"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from internet (redirect)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all egress (restricted by target SG rules anyway)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-alb" })
}

resource "aws_security_group" "traefik" {
  name        = "${var.name_prefix}-sg-traefik"
  description = "Traefik SG: receives HTTP from ALB, routes to services"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "HTTP from ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Allow all egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-traefik" })
}

resource "aws_security_group" "services" {
  name        = "${var.name_prefix}-sg-services"
  description = "App services behind Traefik"
  vpc_id      = aws_vpc.this.id

  dynamic "ingress" {
    for_each = toset(var.service_ports)
    content {
      description     = "From Traefik to service port ${ingress.value}"
      from_port       = ingress.value
      to_port         = ingress.value
      protocol        = "tcp"
      security_groups = [aws_security_group.traefik.id]
    }
  }

  egress {
    description = "Allow all egress (to RDS/Redis/MQ, internet via NAT, etc.)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-services" })
}

resource "aws_security_group_rule" "services_self_ingress" {
  type              = "ingress"
  description       = "Service-to-service (same SG)"
  security_group_id = aws_security_group.services.id

  from_port = 0
  to_port   = 65535
  protocol  = "tcp"

  source_security_group_id = aws_security_group.services.id
}

resource "aws_security_group" "data" {
  name        = "${var.name_prefix}-sg-data"
  description = "Data tier SG (RDS/ElastiCache/AmazonMQ)"
  vpc_id      = aws_vpc.this.id


  ingress {
    description     = "Postgres from services"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  ingress {
    description     = "Redis from services"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.services.id]
  }

  egress {
    description = "Allow all egress (generally fine for managed services)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-sg-data" })
}