output "eks_cluster_role_arn" {
  description = "ARN of the EKS cluster IAM role"
  value       = length(aws_iam_role.eks_cluster) > 0 ? aws_iam_role.eks_cluster[0].arn : ""
}

output "eks_node_role_arn" {
  description = "ARN of the EKS node IAM role"
  value       = length(aws_iam_role.eks_node) > 0 ? aws_iam_role.eks_node[0].arn : ""
}

output "ebs_csi_role_arn" {
  description = "ARN of the EBS CSI driver IRSA role"
  value       = length(aws_iam_role.ebs_csi) > 0 ? aws_iam_role.ebs_csi[0].arn : ""
}

output "alb_controller_role_arn" {
  description = "ARN of the ALB controller IRSA role"
  value       = length(aws_iam_role.alb_controller) > 0 ? aws_iam_role.alb_controller[0].arn : ""
}
