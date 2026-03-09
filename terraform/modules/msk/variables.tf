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

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
  default     = "10.0.0.0/16"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "List of private subnet IDs for MSK"
}

variable "eks_security_group" {
  type        = string
  description = "Security group ID of EKS nodes"
}

variable "eks_node_role_id" {
  type        = string
  description = "IAM role ID of EKS nodes"
}

variable "kafka_version" {
  type        = string
  description = "Kafka version"
  default     = "3.7.0"
}

variable "broker_node_group_info" {
  type = object({
    instance_type = string
    storage_info = object({
      ebs_storage_info = object({
        volume_size = number
      })
    })
  })
  description = "MSK broker node group configuration"
}

variable "tags" {
  type        = map(string)
  description = "Common tags to apply to resources"
  default     = {}
}
