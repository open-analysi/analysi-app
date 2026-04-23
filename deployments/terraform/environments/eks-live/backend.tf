# S3 backend for Terraform state.
# Run scripts/k8s/bootstrap-terraform-backend.sh once before first use.

terraform {
  backend "s3" {
    bucket         = "analysi-terraform-state"
    key            = "eks-live/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "analysi-terraform-locks"
    encrypt        = true
  }
}
