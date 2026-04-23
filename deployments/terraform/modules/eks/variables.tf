variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.31"

  validation {
    condition     = contains(["1.29", "1.30", "1.31", "1.32"], var.kubernetes_version)
    error_message = "kubernetes_version must be a supported EKS version (1.29–1.32)."
  }
}

variable "cluster_role_arn" {
  description = "IAM role ARN for the EKS cluster"
  type        = string
}

variable "node_role_arn" {
  description = "IAM role ARN for EKS worker nodes"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for EKS nodes"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

variable "node_instance_type" {
  description = "EC2 instance type for EKS nodes"
  type        = string
  default     = "t3.large"
}

variable "node_desired_size" {
  description = "Desired number of nodes"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of nodes"
  type        = number
  default     = 3
}

variable "endpoint_public_access" {
  description = "Enable public access to the EKS API endpoint"
  type        = bool
  default     = true
}

variable "public_access_cidrs" {
  description = "CIDR blocks allowed to access the EKS API endpoint. No default — must be explicitly set."
  type        = list(string)

  validation {
    condition     = !contains(var.public_access_cidrs, "0.0.0.0/0")
    error_message = "public_access_cidrs must not contain 0.0.0.0/0. Restrict to specific IPs."
  }
}

variable "cluster_log_types" {
  description = "EKS control plane log types to enable. Empty list disables logging."
  type        = list(string)
  default     = ["audit", "authenticator"]
}

variable "secrets_encryption_kms_key_arn" {
  description = "KMS key ARN for envelope encryption of Kubernetes secrets. Empty string disables encryption."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
