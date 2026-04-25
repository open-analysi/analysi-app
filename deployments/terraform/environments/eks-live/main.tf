# EKS Live Environment
# All-in-cluster deployment: EKS + in-cluster deps (PostgreSQL, Valkey, MinIO, Vault).
# No managed AWS services (RDS, S3, ElastiCache) — future variant.
#
# Usage:
#   make eks-up              # terraform init + apply + configure kubeconfig
#   make eks-down            # terraform destroy (with confirmation)
#   make eks-deploy          # helm upgrade only (no infra changes)
#
# Prerequisites: AWS credentials, terraform, kubectl, helm

terraform {
  required_version = ">= 1.5, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

locals {
  name_prefix  = "${var.project_name}-${var.environment}"
  cluster_name = "${var.project_name}-${var.environment}"
  namespace    = "analysi"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ──── Network ─────────────────────────────────

module "network" {
  source = "../../modules/network"

  name_prefix  = local.name_prefix
  cluster_name = local.cluster_name
  vpc_cidr     = var.vpc_cidr
  tags         = local.common_tags
}

# ──── IAM (cluster + node roles) ──────────────

module "iam_base" {
  source = "../../modules/iam"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

# ──── EKS Cluster ─────────────────────────────

module "eks" {
  source = "../../modules/eks"

  cluster_name        = local.cluster_name
  kubernetes_version  = var.kubernetes_version
  cluster_role_arn    = module.iam_base.eks_cluster_role_arn
  node_role_arn       = module.iam_base.eks_node_role_arn
  private_subnet_ids  = module.network.private_subnet_ids
  public_subnet_ids   = module.network.public_subnet_ids
  node_instance_type  = var.node_instance_type
  node_desired_size   = var.node_desired_size
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size
  public_access_cidrs = var.public_access_cidrs
  tags                = local.common_tags
}

# ──── IAM (IRSA roles — need OIDC from EKS) ─────

module "iam_irsa" {
  source = "../../modules/iam"

  name_prefix       = local.name_prefix
  create_base_roles = false
  create_irsa_roles = true
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  tags              = local.common_tags
}

# ──── EBS CSI Driver (with IRSA) ────────────────

resource "aws_eks_addon" "ebs_csi" {
  cluster_name             = module.eks.cluster_name
  addon_name               = "aws-ebs-csi-driver"
  service_account_role_arn = module.iam_irsa.ebs_csi_role_arn

  tags = local.common_tags

  depends_on = [module.eks]
}

# ──── Kubernetes & Helm Providers ─────────────

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", local.cluster_name, "--region", var.aws_region]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", local.cluster_name, "--region", var.aws_region]
    }
  }
}

# ──── Credentials ─────────────────────────────

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "random_password" "valkey_password" {
  length  = 32
  special = false
}

resource "random_password" "minio_access_key" {
  length  = 20
  special = false
}

resource "random_password" "minio_secret_key" {
  length  = 40
  special = false
}

resource "random_password" "vault_token" {
  length  = 32
  special = false
}

resource "random_password" "system_api_key" {
  length  = 48
  special = false
}

resource "random_password" "admin_api_key" {
  length  = 48
  special = false
}

resource "random_password" "owner_api_key" {
  length  = 48
  special = false
}

# ──── gp3 StorageClass ──────────────────────────
# EBS CSI creates gp2 by default. We use gp3 (better perf, same cost).

resource "kubernetes_storage_class" "gp3" {
  metadata {
    name = "gp3"
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type   = "gp3"
    fsType = "ext4"
  }

  depends_on = [aws_eks_addon.ebs_csi]
}

# ──── Namespace ──────────────────────────────
# Dedicated namespace for workload isolation (not default).

resource "kubernetes_namespace" "analysi" {
  metadata {
    name = local.namespace
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# ──── GHCR Pull Secret ────────────────────────

resource "kubernetes_secret" "ghcr" {
  count = var.ghcr_pat != "" ? 1 : 0

  metadata {
    name      = "ghcr-secret"
    namespace = local.namespace
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "ghcr.io" = {
          username = var.ghcr_username
          password = var.ghcr_pat
          auth     = base64encode("${var.ghcr_username}:${var.ghcr_pat}")
        }
      }
    })
  }
}

# ──── Flyway SQL ConfigMap ────────────────────

resource "kubernetes_config_map" "flyway_sql" {
  metadata {
    name      = "flyway-sql"
    namespace = local.namespace
  }

  # Load all SQL migration files
  data = {
    for f in fileset("${path.module}/../../../../migrations/flyway/sql", "*.sql") :
    f => file("${path.module}/../../../../migrations/flyway/sql/${f}")
  }
}

# ──── ALB Controller (Helm) ───────────────────

resource "helm_release" "alb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"
  version    = "1.11.0"

  set {
    name  = "clusterName"
    value = local.cluster_name
  }

  set {
    name  = "serviceAccount.create"
    value = "true"
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = module.iam_irsa.alb_controller_role_arn
  }

  set {
    name  = "region"
    value = var.aws_region
  }

  set {
    name  = "vpcId"
    value = module.network.vpc_id
  }

  depends_on = [module.eks]
}

# ──── Analysi (Helm) ──────────────────────────

resource "helm_release" "analysi" {
  name             = "analysi"
  chart            = "${path.module}/../../../helm/analysi"
  namespace        = local.namespace
  create_namespace = false
  timeout          = 600

  values = [
    file("${path.module}/../../../helm/analysi/values/eks-live.yaml")
  ]

  # Pin unified app image to the requested version
  set {
    name  = "global.image.tag"
    value = var.image_tag
  }

  set {
    name  = "ui.image.tag"
    value = var.image_tag
  }

  # Override placeholder passwords with generated ones
  set_sensitive {
    name  = "global.database.password"
    value = random_password.db_password.result
  }

  set_sensitive {
    name  = "global.valkey.password"
    value = random_password.valkey_password.result
  }

  set_sensitive {
    name  = "global.minio.accessKey"
    value = random_password.minio_access_key.result
  }

  set_sensitive {
    name  = "global.minio.secretKey"
    value = random_password.minio_secret_key.result
  }

  set_sensitive {
    name  = "global.vault.token"
    value = random_password.vault_token.result
  }

  set_sensitive {
    name  = "global.auth.systemApiKey"
    value = random_password.system_api_key.result
  }

  set_sensitive {
    name  = "global.auth.adminApiKey"
    value = random_password.admin_api_key.result
  }

  set_sensitive {
    name  = "global.auth.ownerApiKey"
    value = random_password.owner_api_key.result
  }

  # Match passwords in dependency service configs
  set_sensitive {
    name  = "postgresql.auth.password"
    value = random_password.db_password.result
  }

  set_sensitive {
    name  = "valkey.auth.password"
    value = random_password.valkey_password.result
  }

  set_sensitive {
    name  = "minio.auth.rootUser"
    value = random_password.minio_access_key.result
  }

  set_sensitive {
    name  = "minio.auth.rootPassword"
    value = random_password.minio_secret_key.result
  }

  set_sensitive {
    name  = "vault.devRootToken"
    value = random_password.vault_token.result
  }

  set {
    name  = "flyway.sqlConfigMap"
    value = "flyway-sql"
  }

  # Restrict ALB access to the same CIDRs as the EKS API
  set {
    name  = "api.ingress.annotations.alb\\.ingress\\.kubernetes\\.io/inbound-cidrs"
    value = join("\\,", var.public_access_cidrs)
  }

  # TLS: when ACM cert is provided, upgrade ALB to HTTPS-only
  dynamic "set" {
    for_each = var.acm_certificate_arn != "" ? [1] : []
    content {
      name  = "api.ingress.annotations.alb\\.ingress\\.kubernetes\\.io/certificate-arn"
      value = var.acm_certificate_arn
    }
  }

  dynamic "set" {
    for_each = var.acm_certificate_arn != "" ? [1] : []
    content {
      name  = "api.ingress.annotations.alb\\.ingress\\.kubernetes\\.io/listen-ports"
      value = "[{\"HTTPS\":443}]"
    }
  }

  dynamic "set" {
    for_each = var.acm_certificate_arn != "" ? [1] : []
    content {
      name  = "api.ingress.annotations.alb\\.ingress\\.kubernetes\\.io/ssl-policy"
      value = "ELBSecurityPolicy-TLS13-1-2-2021-06"
    }
  }

  depends_on = [
    kubernetes_namespace.analysi,
    helm_release.alb_controller,
    kubernetes_config_map.flyway_sql,
    kubernetes_secret.ghcr,
  ]
}
