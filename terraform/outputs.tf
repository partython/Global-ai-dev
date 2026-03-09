# ─── VPC Outputs ───────────────────────────────────────────────────────────────
output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

# ─── EKS Outputs ──────────────────────────────────────────────────────────────
output "eks_cluster_id" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_arn" {
  description = "ARN of the EKS cluster"
  value       = module.eks.cluster_arn
}

output "eks_cluster_endpoint" {
  description = "Endpoint of the EKS cluster"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_certificate_authority" {
  description = "Certificate authority data for EKS cluster"
  value       = module.eks.cluster_certificate_authority
  sensitive   = true
}

output "eks_cluster_version" {
  description = "Kubernetes version running on the EKS cluster"
  value       = module.eks.cluster_version
}

output "eks_oidc_provider_arn" {
  description = "ARN of the OIDC provider for EKS service accounts"
  value       = module.eks.oidc_provider_arn
}

output "eks_node_security_group_id" {
  description = "Security group ID of EKS nodes"
  value       = module.eks.node_security_group_id
}

# ─── RDS Outputs ──────────────────────────────────────────────────────────────
output "rds_endpoint" {
  description = "Endpoint of the RDS PostgreSQL database"
  value       = module.rds.endpoint
}

output "rds_resource_id" {
  description = "Resource ID of the RDS database"
  value       = module.rds.resource_id
}

output "rds_database_name" {
  description = "Name of the RDS database"
  value       = module.rds.database_name
}

# ─── ElastiCache Outputs (conditional) ────────────────────────────────────────
output "redis_endpoint" {
  description = "Endpoint of the Redis cluster (empty if ElastiCache disabled)"
  value       = var.enable_elasticache ? module.elasticache[0].endpoint : "redis-in-cluster"
}

output "redis_port" {
  description = "Port of the Redis cluster"
  value       = var.enable_elasticache ? module.elasticache[0].port : 6379
}

output "redis_auth_token" {
  description = "Authentication token for Redis (stored in Secrets Manager)"
  value       = var.enable_elasticache ? module.elasticache[0].auth_token_secret_arn : ""
  sensitive   = true
}

# ─── Kafka / SQS Outputs (conditional) ────────────────────────────────────────
output "kafka_bootstrap_brokers" {
  description = "Kafka broker endpoints (empty if MSK disabled, use SQS instead)"
  value       = var.enable_msk ? module.msk[0].bootstrap_brokers : ""
}

output "kafka_bootstrap_brokers_tls" {
  description = "Kafka TLS broker endpoints (empty if MSK disabled)"
  value       = var.enable_msk ? module.msk[0].bootstrap_brokers_tls : ""
}

output "kafka_cluster_arn" {
  description = "ARN of the MSK Kafka cluster (empty if MSK disabled)"
  value       = var.enable_msk ? module.msk[0].cluster_arn : ""
}

output "kafka_zookeeper_connect" {
  description = "Zookeeper connection string (empty if MSK disabled)"
  value       = var.enable_msk ? module.msk[0].zookeeper_connect : ""
}

output "sqs_inbound_queue_url" {
  description = "SQS inbound messages queue URL (empty if MSK enabled)"
  value       = var.enable_msk ? "" : aws_sqs_queue.inbound_messages[0].url
}

output "sqs_outbound_queue_url" {
  description = "SQS outbound messages queue URL (empty if MSK enabled)"
  value       = var.enable_msk ? "" : aws_sqs_queue.outbound_messages[0].url
}

output "sqs_events_queue_url" {
  description = "SQS events queue URL (empty if MSK enabled)"
  value       = var.enable_msk ? "" : aws_sqs_queue.events[0].url
}

output "sqs_dlq_url" {
  description = "SQS dead letter queue URL (empty if MSK enabled)"
  value       = var.enable_msk ? "" : aws_sqs_queue.dlq[0].url
}

# ─── Convenience Outputs ──────────────────────────────────────────────────────
output "configure_kubectl_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.aws_region}"
}

output "message_backend" {
  description = "Which message backend is in use"
  value       = var.enable_msk ? "kafka" : "sqs"
}

output "cache_backend" {
  description = "Which cache backend is in use"
  value       = var.enable_elasticache ? "elasticache" : "in-cluster-redis"
}

output "estimated_monthly_cost" {
  description = "Rough monthly cost estimate for this configuration"
  value       = var.enable_msk && var.enable_elasticache ? "$2,500-3,000/mo (full production)" : "$150-200/mo (budget tier)"
}
