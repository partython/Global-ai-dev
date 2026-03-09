output "cluster_id" {
  description = "Redis cluster ID"
  value       = aws_elasticache_cluster.main.cluster_id
}

output "endpoint" {
  description = "Redis primary endpoint address"
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "port" {
  description = "Redis port"
  value       = aws_elasticache_cluster.main.port
}

output "engine_version" {
  description = "Redis engine version"
  value       = aws_elasticache_cluster.main.engine_version
}

output "node_type" {
  description = "Redis node type"
  value       = aws_elasticache_cluster.main.node_type
}

output "num_cache_nodes" {
  description = "Number of cache nodes"
  value       = aws_elasticache_cluster.main.num_cache_nodes
}

output "auth_token_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Redis auth token"
  value       = aws_secretsmanager_secret.redis_auth_token.arn
}

output "kms_key_id" {
  description = "KMS key ID for Redis encryption"
  value       = aws_kms_key.redis.id
}

output "security_group_id" {
  description = "Security group ID of Redis cluster"
  value       = aws_security_group.redis.id
}

output "subnet_group_name" {
  description = "Redis subnet group name"
  value       = aws_elasticache_subnet_group.main.name
}
