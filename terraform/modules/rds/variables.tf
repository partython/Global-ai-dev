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
  description = "List of private subnet IDs for RDS"
}

variable "eks_security_group" {
  type        = string
  description = "Security group ID of EKS nodes"
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class"
  default     = "db.t3.large"
}

variable "allocated_storage" {
  type        = number
  description = "Allocated storage in GB"
  default     = 100
}

variable "backup_retention_days" {
  type        = number
  description = "Number of days to retain backups"
  default     = 7
}

variable "multi_az" {
  type        = bool
  description = "Enable Multi-AZ deployment"
  default     = true
}

variable "skip_final_snapshot" {
  type        = bool
  description = "Skip final snapshot before deletion"
  default     = false
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

variable "enable_proxy" {
  type        = bool
  description = "Enable RDS Proxy for connection pooling"
  default     = true
}
