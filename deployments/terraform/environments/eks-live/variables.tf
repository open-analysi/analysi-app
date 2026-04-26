variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
  default     = "analysi"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "eks-live"

  validation {
    condition     = contains(["eks-live", "eks-staging", "eks-prod"], var.environment)
    error_message = "environment must be one of: eks-live, eks-staging, eks-prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid CIDR block."
  }
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.31"

  validation {
    condition     = contains(["1.29", "1.30", "1.31", "1.32"], var.kubernetes_version)
    error_message = "kubernetes_version must be a supported EKS version (1.29–1.32)."
  }
}

variable "node_instance_type" {
  description = "EC2 instance type for EKS worker nodes"
  type        = string
  default     = "t3.large"
}

variable "node_desired_size" {
  description = "Desired number of EKS worker nodes"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of EKS worker nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of EKS worker nodes"
  type        = number
  default     = 3
}

# ──── Access Control ──────────────────────────

variable "public_access_cidrs" {
  description = "CIDR blocks allowed to access the EKS API and ALB. No default — must be explicitly set."
  type        = list(string)

  validation {
    condition     = !contains(var.public_access_cidrs, "0.0.0.0/0")
    error_message = "public_access_cidrs must not contain 0.0.0.0/0. Restrict to specific IPs."
  }
}

# ──── Image Version ──────────────────────────

variable "image_tag" {
  description = "Container image tag to deploy. Use 'latest' for most recent, or 'sha-<commit>' for a specific version."
  type        = string
  default     = "latest"
}

# ──── TLS (optional) ────────────────────────────

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for ALB HTTPS. When empty, ALB serves HTTP (acceptable for demo with CIDR restriction)."
  type        = string
  default     = ""
}

# ──── GHCR Authentication ─────────────────────

variable "ghcr_username" {
  description = "GitHub username for GHCR image pulls"
  type        = string

  validation {
    condition     = length(var.ghcr_username) > 0
    error_message = "ghcr_username is required. Set it in terraform.tfvars to the GitHub user that owns the PAT."
  }
}

variable "ghcr_pat" {
  description = "GitHub PAT with read:packages scope for GHCR. Set via TF_VAR_ghcr_pat env var — never store in files."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.ghcr_pat) > 0
    error_message = "ghcr_pat is required. Set TF_VAR_ghcr_pat env var. Generate a PAT at https://github.com/settings/tokens with read:packages scope."
  }
}
