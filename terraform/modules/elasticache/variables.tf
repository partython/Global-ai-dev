variable "project" {
  type        = string
  description = "Project name"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "List of private subnet IDs for ElastiCache"
}

variable "eks_security_group" {
  type        = string
  description = "Security group ID of EKS nodes"
}

variable "engine_version" {
  type        = string
  description = "Redis engine version"
  default     = "7.0"
}

variable "node_type" {
  type        = string
  description = "ElastiCache node type"
  default     = "cache.t3.medium"
}

variable "num_cache_nodes" {
  type        = number
  description = "Number of cache nodes"
  default     = 3
}

variable "automatic_failover" {
  type        = bool
  description = "Enable automatic failover"
  default     = true
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
  default     = "10.0.0.0/16"
}

variable "tags" {
  type        = map(string)
  description = "Common tags to apply to resources"
  default     = {}
}
