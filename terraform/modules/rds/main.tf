locals {
  db_name = replace("${var.project}${var.environment}", "-", "")
}

# KMS Key for RDS encryption
resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = var.tags
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.project}-${var.environment}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-db-subnet-group"
    }
  )
}

# Security Group for RDS
resource "aws_security_group" "rds" {
  name_prefix = "${var.project}-${var.environment}-rds-sg"
  vpc_id      = var.vpc_id
  description = "Security group for RDS PostgreSQL"

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_security_group]
    description     = "Allow from EKS nodes"
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    # Restricted to VPC CIDR — RDS only needs outbound for Multi-AZ replication
    # and AWS service endpoints (KMS, S3 for backups) via VPC endpoints
    cidr_blocks = [var.vpc_cidr]
    description = "Allow HTTPS to VPC for AWS service endpoints"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-rds-sg"
    }
  )
}

# DB Parameter Group with RLS-friendly settings
resource "aws_db_parameter_group" "main" {
  family      = "postgres16"
  name_prefix = "${var.project}-${var.environment}"
  description = "Parameter group for ${var.project} PostgreSQL"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  parameter {
    name  = "max_connections"
    value = "500"
  }

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-db-param-group"
    }
  )
}

# RDS PostgreSQL Instance
resource "aws_db_instance" "main" {
  identifier             = "${var.project}-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16.1"
  instance_class         = var.db_instance_class
  allocated_storage      = var.allocated_storage
  storage_type           = "gp3"
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.rds.arn

  db_name                = local.db_name
  username               = "admin"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  multi_az               = var.multi_az
  backup_retention_period = var.backup_retention_days
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  skip_final_snapshot    = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.project}-${var.environment}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  copy_tags_to_snapshot  = true

  deletion_protection    = var.environment == "production" ? true : false

  enabled_cloudwatch_logs_exports = [
    "postgresql"
  ]

  performance_insights_enabled = true
  performance_insights_kms_key_id = aws_kms_key.rds.arn
  performance_insights_retention_period = var.environment == "production" ? 31 : 7

  enable_iam_database_authentication = true

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-postgres"
    }
  )

  depends_on = [aws_db_subnet_group.main]
}

# ─── RDS Proxy (conditional — saves ~$20/mo when disabled) ────────────────────
resource "aws_db_proxy" "main" {
  count                  = var.enable_proxy ? 1 : 0
  name                   = "${var.project}-${var.environment}-proxy"
  engine_family          = "POSTGRESQL"
  auth {
    auth_scheme = "SECRETS"
    secret_arn  = aws_secretsmanager_secret.db_credentials.arn
  }
  role_arn               = aws_iam_role.proxy[0].arn
  database_vpc_subnet_ids = var.private_subnet_ids
  vpc_security_group_ids = [aws_security_group.rds_proxy[0].id]

  max_idle_connections_percent    = 50
  max_connections_percent         = 100
  connection_borrow_timeout        = 120
  session_pinning_filters          = []
  init_query                       = ""
  require_tls                      = true

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-db-proxy"
    }
  )

  depends_on = [
    aws_iam_role_policy.proxy
  ]
}

resource "aws_db_proxy_target_group" "main" {
  count                   = var.enable_proxy ? 1 : 0
  db_proxy_name          = aws_db_proxy.main[0].name
  name                   = "default"
  db_parameter_group_name = aws_db_parameter_group.main.name
}

resource "aws_db_proxy_target" "main" {
  count                  = var.enable_proxy ? 1 : 0
  db_proxy_name         = aws_db_proxy.main[0].name
  target_group_name     = aws_db_proxy_target_group.main[0].name
  db_instance_identifier = aws_db_instance.main.id
}

resource "aws_security_group" "rds_proxy" {
  count       = var.enable_proxy ? 1 : 0
  name_prefix = "${var.project}-${var.environment}-rds-proxy-sg"
  vpc_id      = var.vpc_id
  description = "Security group for RDS Proxy"

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_security_group]
    description     = "Allow from EKS nodes"
  }

  egress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.rds.id]
    description     = "Allow to RDS instance"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-rds-proxy-sg"
    }
  )
}

resource "aws_iam_role" "proxy" {
  count = var.enable_proxy ? 1 : 0
  name  = "${var.project}-${var.environment}-rds-proxy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "proxy" {
  count = var.enable_proxy ? 1 : 0
  name  = "${var.project}-${var.environment}-rds-proxy-policy"
  role  = aws_iam_role.proxy[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Effect   = "Allow"
        Resource = aws_secretsmanager_secret.db_credentials.arn
      }
    ]
  })
}

# Secrets Manager for DB credentials
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project}-${var.environment}-db-credentials"
  recovery_window_in_days = 7

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-db-credentials"
    }
  )
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = aws_db_instance.main.username
    password = aws_db_instance.main.master_user_secret[0].secret_string
    engine   = "postgres"
    host     = aws_db_instance.main.endpoint
    port     = 5432
    dbname   = aws_db_instance.main.db_name
  })
}

# CloudWatch Alarms for RDS
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${var.project}-${var.environment}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alert when RDS CPU exceeds 80%"
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
  alarm_actions = []

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${var.project}-${var.environment}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5368709120 # 5GB
  alarm_description   = "Alert when RDS free storage is below 5GB"
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }
  alarm_actions = []

  tags = var.tags
}
