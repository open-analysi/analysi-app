variable "name_prefix" {
  description = "Prefix for all resource names"
  type        = string
}

variable "create_base_roles" {
  description = "Create EKS cluster and node IAM roles. Set false when only ALB IRSA is needed."
  type        = bool
  default     = true
}

variable "create_irsa_roles" {
  description = "Create IRSA roles (EBS CSI, ALB controller). Requires oidc_provider_arn and oidc_provider_url."
  type        = bool
  default     = false
}

variable "oidc_provider_arn" {
  description = "EKS OIDC provider ARN (for IRSA)."
  type        = string
  default     = ""
}

variable "oidc_provider_url" {
  description = "EKS OIDC provider URL without https:// prefix"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
