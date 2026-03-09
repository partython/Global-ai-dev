# KMS Key for ElastiCache encryption
resource "aws_kms_key" "redis" {
  description             = "KMS key for Redis encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = var.tags
}

resource "aws_kms_alias" "redis" {
  name          = "alias/${var.project}-${var.environment}-redis"
  target_key_id = aws_kms_key.redis.key_id
}

# Subnet Group for ElastiCache
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-redis-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-subnet-group"
    }
  )
}

# Security Group for Redis
resource "aws_security_group" "redis" {
  name_prefix = "${var.project}-${var.environment}-redis-sg"
  vpc_id      = var.vpc_id
  description = "Security group for Redis cluster"

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.eks_security_group]
    description     = "Allow from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    # NOTE: ElastiCache requires outbound access for replication and cluster operations
    # 0.0.0.0/0 allows necessary AWS service communications for failover
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-sg"
    }
  )
}

# Random password for Redis auth token
resource "random_password" "redis_auth_token" {
  length  = 32
  special = true
}

# Secrets Manager for Redis auth token
resource "aws_secretsmanager_secret" "redis_auth_token" {
  name                    = "${var.project}-${var.environment}-redis-auth-token"
  recovery_window_in_days = 7

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-auth-token"
    }
  )
}

resource "aws_secretsmanager_secret_version" "redis_auth_token" {
  secret_id      = aws_secretsmanager_secret.redis_auth_token.id
  secret_string  = random_password.redis_auth_token.result
}

# ElastiCache Redis Cluster with cluster mode enabled
resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${var.project}-${var.environment}-redis"
  engine               = "redis"
  node_type            = var.node_type
  num_cache_nodes      = var.num_cache_nodes
  parameter_group_name = aws_elasticache_parameter_group.main.name
  engine_version       = var.engine_version
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.main.name
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  # Encryption
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.redis.arn
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth_token.result
  auth_token_update_strategy = "ROTATE"

  # Availability
  automatic_failover_enabled = var.automatic_failover
  multi_az_enabled           = var.automatic_failover && var.num_cache_nodes > 1

  # Logging
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow_log.name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
    enabled          = true
  }

  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_engine_log.name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "engine-log"
    enabled          = true
  }

  snapshot_retention_limit = 5
  snapshot_window          = "03:00-05:00"

  maintenance_window = "mon:04:00-mon:06:00"

  notification_topic_arn = aws_sns_topic.redis_notifications.arn

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis"
    }
  )

  depends_on = [
    aws_elasticache_parameter_group.main,
    aws_elasticache_subnet_group.main
  ]
}

# Parameter Group
resource "aws_elasticache_parameter_group" "main" {
  name_prefix = "${var.project}-${var.environment}"
  family      = "redis7"
  description = "Parameter group for ${var.project} Redis"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }

  parameter {
    name  = "timeout"
    value = "300"
  }

  parameter {
    name  = "tcp-keepalive"
    value = "300"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-param-group"
    }
  )
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "redis_slow_log" {
  name              = "/aws/elasticache/${var.project}-${var.environment}/slow-log"
  retention_in_days = 7

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-slow-log"
    }
  )
}

resource "aws_cloudwatch_log_group" "redis_engine_log" {
  name              = "/aws/elasticache/${var.project}-${var.environment}/engine-log"
  retention_in_days = 7

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-engine-log"
    }
  )
}

# SNS Topic for notifications
resource "aws_sns_topic" "redis_notifications" {
  name              = "${var.project}-${var.environment}-redis-notifications"
  kms_master_key_id = "alias/aws/sns"

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-redis-notifications"
    }
  )
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  alarm_name          = "${var.project}-${var.environment}-redis-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "EngineCPUUtilization"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 75
  alarm_description   = "Alert when Redis CPU exceeds 75%"
  dimensions = {
    CacheClusterId = aws_elasticache_cluster.main.cluster_id
  }
  alarm_actions = [aws_sns_topic.redis_notifications.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "redis_memory" {
  alarm_name          = "${var.project}-${var.environment}-redis-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseMemoryUsagePercentage"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alert when Redis memory exceeds 80%"
  dimensions = {
    CacheClusterId = aws_elasticache_cluster.main.cluster_id
  }
  alarm_actions = [aws_sns_topic.redis_notifications.arn]

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "redis_evictions" {
  alarm_name          = "${var.project}-${var.environment}-redis-evictions"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Evictions"
  namespace           = "AWS/ElastiCache"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when Redis is evicting keys"
  dimensions = {
    CacheClusterId = aws_elasticache_cluster.main.cluster_id
  }
  alarm_actions = [aws_sns_topic.redis_notifications.arn]

  tags = var.tags
}
