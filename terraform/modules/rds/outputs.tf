output "instance_id" {
  description = "RDS instance identifier"
  value       = aws_db_instance.main.id
}

output "instance_arn" {
  description = "RDS instance ARN"
  value       = aws_db_instance.main.arn
}

output "endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.main.endpoint
}

output "address" {
  description = "RDS instance address"
  value       = aws_db_instance.main.address
}

output "port" {
  description = "RDS instance port"
  value       = aws_db_instance.main.port
}

output "database_name" {
  description = "RDS database name"
  value       = aws_db_instance.main.db_name
}

output "master_username" {
  description = "RDS master username"
  value       = aws_db_instance.main.username
  sensitive   = true
}

output "resource_id" {
  description = "RDS resource ID"
  value       = aws_db_instance.main.resource_id
}

output "proxy_endpoint" {
  description = "RDS Proxy endpoint (empty if proxy disabled)"
  value       = var.enable_proxy ? aws_db_proxy.main[0].endpoint : ""
}

output "secrets_manager_secret_arn" {
  description = "Secrets Manager secret ARN containing DB credentials"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "security_group_id" {
  description = "Security group ID of RDS instance"
  value       = aws_security_group.rds.id
}

output "kms_key_id" {
  description = "KMS key ID for RDS encryption"
  value       = aws_kms_key.rds.id
}
