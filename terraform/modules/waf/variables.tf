variable "environment" {
  type        = string
  description = "Environment name"
}

variable "project" {
  type        = string
  description = "Project name"
}

variable "rate_limit" {
  type        = number
  description = "Max requests per 5-minute window per IP"
  default     = 2000
}

variable "tags" {
  type        = map(string)
  description = "Common tags"
  default     = {}
}
