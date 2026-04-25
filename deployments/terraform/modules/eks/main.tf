# EKS module — cluster, managed node group, OIDC provider

resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  role_arn = var.cluster_role_arn
  version  = var.kubernetes_version

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    endpoint_private_access = true
    endpoint_public_access  = var.endpoint_public_access
    public_access_cidrs     = var.public_access_cidrs
  }

  # Control plane logging — audit + authenticator for security visibility
  enabled_cluster_log_types = var.cluster_log_types

  # Envelope encryption for Kubernetes secrets at rest
  dynamic "encryption_config" {
    for_each = var.secrets_encryption_kms_key_arn != "" ? [1] : []
    content {
      provider {
        key_arn = var.secrets_encryption_kms_key_arn
      }
      resources = ["secrets"]
    }
  }

  tags = var.tags
}

# ──── OIDC Provider (for IRSA) ────────────────

data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer

  tags = var.tags
}

# ──── Managed Node Group ──────────────────────

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.cluster_name}-nodes"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids

  instance_types = [var.node_instance_type]

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  tags = var.tags

  depends_on = [aws_eks_cluster.main]
}

# ──── CoreDNS + kube-proxy (managed add-ons) ──

# Pin addon versions to prevent surprise upgrades during terraform apply.
# Find latest: aws eks describe-addon-versions --addon-name <name> --kubernetes-version 1.31

resource "aws_eks_addon" "coredns" {
  cluster_name  = aws_eks_cluster.main.name
  addon_name    = "coredns"
  addon_version = "v1.11.4-eksbuild.28"

  tags = var.tags

  depends_on = [aws_eks_node_group.main]
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name  = aws_eks_cluster.main.name
  addon_name    = "kube-proxy"
  addon_version = "v1.31.14-eksbuild.5"

  tags = var.tags

  depends_on = [aws_eks_node_group.main]
}

resource "aws_eks_addon" "vpc_cni" {
  cluster_name  = aws_eks_cluster.main.name
  addon_name    = "vpc-cni"
  addon_version = "v1.21.1-eksbuild.3"

  tags = var.tags

  depends_on = [aws_eks_node_group.main]
}
