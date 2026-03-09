# KMS Key for MSK encryption
resource "aws_kms_key" "msk" {
  description             = "KMS key for MSK encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = var.tags
}

resource "aws_kms_alias" "msk" {
  name          = "alias/${var.project}-${var.environment}-msk"
  target_key_id = aws_kms_key.msk.key_id
}

# Security Group for MSK
resource "aws_security_group" "msk" {
  name_prefix = "${var.project}-${var.environment}-msk-sg"
  vpc_id      = var.vpc_id
  description = "Security group for MSK cluster"

  # Allow from EKS nodes
  ingress {
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [var.eks_security_group]
    description     = "Plaintext broker communication from EKS nodes"
  }

  # Allow TLS broker communication
  ingress {
    from_port       = 9094
    to_port         = 9094
    protocol        = "tcp"
    security_groups = [var.eks_security_group]
    description     = "TLS broker communication from EKS nodes"
  }

  # Allow Zookeeper communication within cluster
  ingress {
    from_port   = 2181
    to_port     = 2181
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "Zookeeper client communication"
  }

  # Allow broker internal communication
  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "Internal broker communication"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    # NOTE: MSK requires outbound access for broker coordination and metadata services
    # 0.0.0.0/0 allows necessary AWS service communications
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-msk-sg"
    }
  )
}

# CloudWatch Log Group for MSK
resource "aws_cloudwatch_log_group" "msk_broker" {
  name              = "/aws/msk/${var.project}-${var.environment}/broker"
  retention_in_days = 7

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-msk-broker-logs"
    }
  )
}

# IAM Role for MSK CloudWatch Logs
resource "aws_iam_role" "msk_cloudwatch_logs" {
  name = "${var.project}-${var.environment}-msk-cloudwatch-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "kafka.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "msk_cloudwatch_logs" {
  name = "${var.project}-${var.environment}-msk-cloudwatch-logs-policy"
  role = aws_iam_role.msk_cloudwatch_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogStream",
          "logs:CreateLogGroup"
        ]
        Effect   = "Allow"
        Resource = "${aws_cloudwatch_log_group.msk_broker.arn}:*"
      }
    ]
  })
}

# MSK Cluster
resource "aws_msk_cluster" "main" {
  cluster_name           = "${var.project}-${var.environment}"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = length(var.private_subnet_ids) >= 3 ? 3 : length(var.private_subnet_ids)

  broker_node_group_info {
    instance_type   = var.broker_node_group_info.instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]
    az_distribution = "DEFAULT"

    storage_info {
      ebs_storage_info {
        volume_size            = var.broker_node_group_info.storage_info.ebs_storage_info.volume_size
        iops                   = 3000
        throughput             = 125
        provisioned_throughput {
          enabled           = false
        }
      }
    }

    cloudwatch_logs_enabled = true
    cloudwatch_logs_log_group = aws_cloudwatch_log_group.msk_broker.name

    monitoring_info {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk_broker.name
      }
      prometheus {
        jmx_exporter {
          enabled_in_broker = false
        }
        node_exporter {
          enabled_in_broker = false
        }
      }
    }
  }

  cluster_configuration {
    instance_type   = var.broker_node_group_info.instance_type
    kafka_version   = var.kafka_version
    num_partitions  = 3
    replication_factor = 3
  }

  encryption_info {
    client_broker = "TLS"
    in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
    at_rest {
      data_volume_kms_key_id = aws_kms_key.msk.arn
    }
  }

  client_authentication {
    sasl {
      iam   = true
      plain = false
      scram = false
    }
    tls {
      certificate_authority_arns = []
      enabled                    = true
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk_broker.name
      }
      firehose {
        enabled         = false
        delivery_stream = null
      }
      s3 {
        enabled = false
        bucket  = null
      }
    }
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project}-${var.environment}-msk"
    }
  )

  depends_on = [
    aws_iam_role_policy.msk_cloudwatch_logs,
    aws_cloudwatch_log_group.msk_broker
  ]
}

# IAM Policy for EKS nodes to access MSK
resource "aws_iam_role_policy" "eks_msk_access" {
  name = "${var.project}-${var.environment}-eks-msk-access"
  role = var.eks_node_role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kafka-cluster:Connect",
          "kafka-cluster:AlterCluster",
          "kafka-cluster:DescribeCluster"
        ]
        Resource = aws_msk_cluster.main.arn
      },
      {
        Effect = "Allow"
        Action = [
          "kafka-cluster:*Topic*",
          "kafka-cluster:WriteData",
          "kafka-cluster:ReadData"
        ]
        Resource = "${aws_msk_cluster.main.arn}:topic/*"
      },
      {
        Effect = "Allow"
        Action = [
          "kafka-cluster:AlterGroup",
          "kafka-cluster:DescribeGroup"
        ]
        Resource = "${aws_msk_cluster.main.arn}:group/*"
      }
    ]
  })
}

# CloudWatch Alarms for MSK
resource "aws_cloudwatch_metric_alarm" "msk_broker_disk_space" {
  alarm_name          = "${var.project}-${var.environment}-msk-broker-disk-space-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "KafkaDiskUsed"
  namespace           = "AWS/Kafka"
  period              = 300
  statistic           = "Average"
  threshold           = 10737418240 # 10GB
  alarm_description   = "Alert when MSK broker disk space is below 10GB"
  dimensions = {
    Cluster = aws_msk_cluster.main.cluster_name
  }
  alarm_actions = []

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "msk_cpu_utilization" {
  alarm_name          = "${var.project}-${var.environment}-msk-cpu-utilization-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CpuUser"
  namespace           = "AWS/Kafka"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alert when MSK CPU utilization exceeds 80%"
  dimensions = {
    Cluster = aws_msk_cluster.main.cluster_name
  }
  alarm_actions = []

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "msk_bytes_in_per_sec" {
  alarm_name          = "${var.project}-${var.environment}-msk-bytes-in-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "BytesInPerSec"
  namespace           = "AWS/Kafka"
  period              = 300
  statistic           = "Average"
  threshold           = 10485760 # 10MB/s
  alarm_description   = "Alert when MSK incoming bytes exceed 10MB/s"
  dimensions = {
    Cluster = aws_msk_cluster.main.cluster_name
  }
  alarm_actions = []

  tags = var.tags
}
