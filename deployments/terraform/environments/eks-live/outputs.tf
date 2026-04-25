output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.aws_region}"
}

output "api_admin_key" {
  description = "Admin API key for accessing the API"
  value       = random_password.admin_api_key.result
  sensitive   = true
}

output "deployment_summary" {
  description = "Deployment info"
  value       = <<-EOT

    ╔══════════════════════════════════════════════════════╗
    ║              Analysi EKS Live Deployment            ║
    ╠══════════════════════════════════════════════════════╣
    ║                                                      ║
    ║  Cluster: ${module.eks.cluster_name}
    ║  Region:  ${var.aws_region}
    ║                                                      ║
    ║  Configure kubectl:                                  ║
    ║    aws eks update-kubeconfig \                        ║
    ║      --name ${module.eks.cluster_name} \
    ║      --region ${var.aws_region}
    ║                                                      ║
    ║  Get API URL:                                        ║
    ║    kubectl get ingress                                ║
    ║                                                      ║
    ║  Get admin API key:                                   ║
    ║    terraform output -raw api_admin_key                ║
    ║                                                      ║
    ║  Teardown:                                           ║
    ║    make eks-down                                      ║
    ║                                                      ║
    ╚══════════════════════════════════════════════════════╝
  EOT
}
