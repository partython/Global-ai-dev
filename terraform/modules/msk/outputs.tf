output "cluster_arn" {
  description = "ARN of the MSK cluster"
  value       = aws_msk_cluster.main.arn
}

output "cluster_name" {
  description = "Name of the MSK cluster"
  value       = aws_msk_cluster.main.cluster_name
}

output "bootstrap_brokers" {
  description = "Kafka bootstrap brokers (plaintext)"
  value       = aws_msk_cluster.main.bootstrap_brokers
}

output "bootstrap_brokers_tls" {
  description = "Kafka bootstrap brokers (TLS)"
  value       = aws_msk_cluster.main.bootstrap_brokers_tls
}

output "bootstrap_brokers_iam_sasl" {
  description = "Kafka bootstrap brokers (IAM SASL)"
  value       = aws_msk_cluster.main.bootstrap_brokers_sasl_iam
}

output "zookeeper_connect" {
  description = "Zookeeper connection string"
  value       = aws_msk_cluster.main.zookeeper_connect_string
}

output "kafka_version" {
  description = "Kafka version"
  value       = aws_msk_cluster.main.kafka_version
}

output "number_of_broker_nodes" {
  description = "Number of broker nodes"
  value       = aws_msk_cluster.main.number_of_broker_nodes
}

output "security_group_id" {
  description = "Security group ID of MSK cluster"
  value       = aws_security_group.msk.id
}

output "kms_key_id" {
  description = "KMS key ID for MSK encryption"
  value       = aws_kms_key.msk.id
}
