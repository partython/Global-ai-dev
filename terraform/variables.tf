variable "aws_region" {
  type        = string
  description = "AWS region for all resources"
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Environment name (dev, staging, production)"
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }
}

variable "project" {
  type        = string
  description = "Project name"
  default     = "priya-global"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "List of availability zones for the region"
}

variable "eks_cluster_version" {
  type        = string
  description = "Kubernetes version to use for the EKS cluster"
  default     = "1.29"
}

variable "general_node_group_config" {
  type = object({
    instance_type = string
    min_size      = number
    max_size      = number
    desired_size  = number
    disk_size     = number
  })
  description = "Configuration for general-purpose node group"
  default = {
    instance_type = "t3.xlarge"
    min_size      = 3
    max_size      = 10
    desired_size  = 3
    disk_size     = 50
  }
}

variable "ai_node_group_config" {
  type = object({
    instance_type = string
    min_size      = number
    max_size      = number
    desired_size  = number
    disk_size     = number
  })
  description = "Configuration for AI workload node group"
  default = {
    instance_type = "c5.2xlarge"
    min_size      = 2
    max_size      = 8
    desired_size  = 2
    disk_size     = 100
  }
}

variable "system_node_group_config" {
  type = object({
    instance_type = string
    min_size      = number
    max_size      = number
    desired_size  = number
    disk_size     = number
  })
  description = "Configuration for system/monitoring node group"
  default = {
    instance_type = "t3.large"
    min_size      = 2
    max_size      = 4
    desired_size  = 2
    disk_size     = 30
  }
}

variable "rds_instance_class" {
  type        = string
  description = "RDS instance class"
  default     = "db.t3.large"
}

variable "rds_allocated_storage" {
  type        = number
  description = "Allocated storage for RDS in GB"
  default     = 100
}

variable "rds_backup_retention_days" {
  type        = number
  description = "Number of days to retain RDS backups"
  default     = 7
}

variable "rds_multi_az" {
  type        = bool
  description = "Enable Multi-AZ for RDS"
  default     = true
}

variable "redis_engine_version" {
  type        = string
  description = "Redis engine version"
  default     = "7.0"
}

variable "redis_node_type" {
  type        = string
  description = "ElastiCache node type"
  default     = "cache.t3.medium"
}

variable "redis_num_cache_nodes" {
  type        = number
  description = "Number of cache nodes for Redis"
  default     = 3
}

variable "redis_automatic_failover" {
  type        = bool
  description = "Enable automatic failover for Redis"
  default     = true
}

variable "msk_kafka_version" {
  type        = string
  description = "Kafka version for MSK"
  default     = "3.7.0"
}

variable "msk_broker_node_group_info" {
  type = object({
    instance_type   = string
    client_subnets  = list(string)
    security_groups = list(string)
    storage_info = object({
      ebs_storage_info = object({
        volume_size = number
      })
    })
  })
  description = "MSK broker node group configuration"
  default = {
    instance_type   = "kafka.m5.large"
    client_subnets  = []
    security_groups = []
    storage_info = {
      ebs_storage_info = {
        volume_size = 100
      }
    }
  }
}

# ─── Budget Toggle Variables ───────────────────────────────────────────────────
# These allow disabling expensive managed services for budget deployments.
# When disabled, the application should use in-cluster alternatives:
#   - MSK disabled  → use Amazon SQS or in-cluster Redis pub/sub
#   - ElastiCache disabled → run Redis as a K8s pod
#   - RDS Proxy disabled → connect directly to RDS

variable "enable_msk" {
  type        = bool
  description = "Enable AWS MSK (Managed Kafka). Disable to save ~$400/mo and use SQS instead."
  default     = true
}

variable "enable_elasticache" {
  type        = bool
  description = "Enable AWS ElastiCache Redis. Disable to save ~$400/mo and run Redis in-cluster."
  default     = true
}

variable "enable_rds_proxy" {
  type        = bool
  description = "Enable RDS Proxy for connection pooling. Disable to save ~$20/mo on small deployments."
  default     = true
}

variable "enable_nat_gateway" {
  type        = bool
  description = "Enable NAT Gateway for private subnet internet access. Disable to save ~$45/mo (nodes use public subnets)."
  default     = true
}

variable "enable_vpc_flow_logs" {
  type        = bool
  description = "Enable VPC Flow Logs. Disable to save on CloudWatch costs."
  default     = true
}


variable "waf_rate_limit" {
  type        = number
  description = "Maximum requests per 5-minute window per IP for WAF rate limiting"
  default     = 2000
}
