terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "s3" {
    bucket         = "priya-global-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "priya-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      CreatedAt   = timestamp()
    }
  }
}

# Data sources for EKS cluster authentication
data "aws_eks_cluster" "cluster" {
  name       = module.eks.cluster_name
  depends_on = [module.eks]
}

data "aws_eks_cluster_auth" "cluster" {
  name       = module.eks.cluster_name
  depends_on = [module.eks]
}

# Kubernetes Provider - requires EKS cluster to be created first
provider "kubernetes" {
  host                   = data.aws_eks_cluster.cluster.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.cluster.token
}

# Helm Provider - for deploying Kubernetes packages
provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.cluster.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.cluster.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.cluster.token
  }
}

# ─── VPC Module ────────────────────────────────────────────────────────────────
module "vpc" {
  source             = "./modules/vpc"
  environment        = var.environment
  project            = var.project
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones

  enable_nat_gateway  = var.enable_nat_gateway
  enable_flow_logs    = var.enable_vpc_flow_logs

  tags = local.common_tags
}

# ─── EKS Module ───────────────────────────────────────────────────────────────
module "eks" {
  source                    = "./modules/eks"
  environment               = var.environment
  project                   = var.project
  vpc_id                    = module.vpc.vpc_id
  private_subnet_ids        = module.vpc.private_subnet_ids
  eks_cluster_version       = var.eks_cluster_version
  general_node_group_config = var.general_node_group_config
  ai_node_group_config      = var.ai_node_group_config
  system_node_group_config  = var.system_node_group_config

  tags = local.common_tags
}

# ─── RDS Module (Always enabled — database is essential) ──────────────────────
module "rds" {
  source             = "./modules/rds"
  environment        = var.environment
  project            = var.project
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  eks_security_group = module.eks.node_security_group_id

  db_instance_class      = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage
  backup_retention_days   = var.rds_backup_retention_days
  multi_az               = var.rds_multi_az
  skip_final_snapshot    = var.environment != "production"
  enable_proxy           = var.enable_rds_proxy

  tags = local.common_tags
}

# ─── ElastiCache Redis Module (Conditional — can run Redis in-cluster) ────────
module "elasticache" {
  count = var.enable_elasticache ? 1 : 0

  source             = "./modules/elasticache"
  environment        = var.environment
  project            = var.project
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  eks_security_group = module.eks.node_security_group_id

  engine_version     = var.redis_engine_version
  node_type          = var.redis_node_type
  num_cache_nodes    = var.redis_num_cache_nodes
  automatic_failover = var.redis_automatic_failover

  tags = local.common_tags
}

# ─── MSK Kafka Module (Conditional — can use SQS instead) ─────────────────────
module "msk" {
  count = var.enable_msk ? 1 : 0

  source             = "./modules/msk"
  environment        = var.environment
  project            = var.project
  vpc_id             = module.vpc.vpc_id
  vpc_cidr           = var.vpc_cidr
  private_subnet_ids = module.vpc.private_subnet_ids
  eks_security_group = module.eks.node_security_group_id
  eks_node_role_id   = module.eks.node_role_id

  kafka_version          = var.msk_kafka_version
  broker_node_group_info = var.msk_broker_node_group_info

  tags       = local.common_tags
  depends_on = [module.eks, module.vpc]
}

# ─── SQS Queues (Budget alternative to Kafka) ─────────────────────────────────
# When MSK is disabled, create SQS queues for message passing
resource "aws_sqs_queue" "inbound_messages" {
  count = var.enable_msk ? 0 : 1

  name                       = "${var.project}-${var.environment}-inbound-messages"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 604800 # 7 days (matches Kafka retention)
  receive_wait_time_seconds  = 20     # Long polling
  max_message_size           = 262144 # 256KB

  # ── Security: Server-side encryption ──
  sqs_managed_sse_enabled = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[0].arn
    maxReceiveCount     = 5
  })

  tags = merge(local.common_tags, { Name = "${var.project}-${var.environment}-inbound-messages" })
}

resource "aws_sqs_queue" "outbound_messages" {
  count = var.enable_msk ? 0 : 1

  name                       = "${var.project}-${var.environment}-outbound-messages"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 604800
  receive_wait_time_seconds  = 20
  max_message_size           = 262144

  # ── Security: Server-side encryption ──
  sqs_managed_sse_enabled = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[0].arn
    maxReceiveCount     = 5
  })

  tags = merge(local.common_tags, { Name = "${var.project}-${var.environment}-outbound-messages" })
}

resource "aws_sqs_queue" "events" {
  count = var.enable_msk ? 0 : 1

  name                       = "${var.project}-${var.environment}-events"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 604800
  receive_wait_time_seconds  = 20

  # ── Security: Server-side encryption ──
  sqs_managed_sse_enabled = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[0].arn
    maxReceiveCount     = 5
  })

  tags = merge(local.common_tags, { Name = "${var.project}-${var.environment}-events" })
}

resource "aws_sqs_queue" "dlq" {
  count = var.enable_msk ? 0 : 1

  name                      = "${var.project}-${var.environment}-dlq"
  message_retention_seconds = 1209600 # 14 days

  # ── Security: Server-side encryption ──
  sqs_managed_sse_enabled = true

  tags = merge(local.common_tags, { Name = "${var.project}-${var.environment}-dlq" })
}

# IAM policy for EKS nodes to access SQS (when MSK is disabled)
resource "aws_iam_role_policy" "eks_sqs_access" {
  count = var.enable_msk ? 0 : 1

  name = "${var.project}-${var.environment}-eks-sqs-access"
  role = module.eks.node_role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = [
          aws_sqs_queue.inbound_messages[0].arn,
          aws_sqs_queue.outbound_messages[0].arn,
          aws_sqs_queue.events[0].arn,
          aws_sqs_queue.dlq[0].arn
        ]
      }
    ]
  })
}

# ─── WAF (Web Application Firewall) for ALB ──────────────────────────────────
module "waf" {
  source      = "./modules/waf"
  environment = var.environment
  project     = var.project

  # Rate limiting: max requests per 5-minute window per IP
  rate_limit = var.waf_rate_limit

  tags = local.common_tags
}

# ─── Local variables ──────────────────────────────────────────────────────────
locals {
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
