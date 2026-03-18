locals {
  redis_id = "fm-${local.env}-redis" 
}

resource "aws_elasticache_subnet_group" "redis" {
  count      = var.enable_redis ? 1 : 0
  name       = "${local.redis_id}-subnets"
  subnet_ids = module.network.private_data_subnet_ids
  tags       = local.common_tags
}

resource "aws_elasticache_replication_group" "redis" {
  count = var.enable_redis ? 1 : 0

  replication_group_id       = local.redis_id
  description                = "Redis for NiceGUI/session storage (${local.project}-${local.env})"

  engine                     = "redis"
  port                       = 6379
  node_type                  = var.redis_node_type

  num_cache_clusters         = 1
  automatic_failover_enabled = false
  multi_az_enabled           = false

  subnet_group_name          = aws_elasticache_subnet_group.redis[0].name
  security_group_ids         = [module.network.sg_data_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = false

  tags = local.common_tags
}

locals {
  redis_primary_endpoint = var.enable_redis ? aws_elasticache_replication_group.redis[0].primary_endpoint_address : null
}

output "redis_primary_endpoint" {
  value = local.redis_primary_endpoint
}