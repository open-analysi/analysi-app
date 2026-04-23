# EKS Live Environment

All-in-cluster EKS deployment. No managed AWS services — everything runs in containers
with persistent volumes (EBS gp3) for PostgreSQL and MinIO.

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` works)
- Terraform >= 1.5
- kubectl
- Helm 3
- GitHub PAT with `read:packages` scope (for GHCR image pulls)

## First-Time Setup

Bootstrap the Terraform state backend (S3 + DynamoDB):

```bash
make eks-bootstrap
```

Create `terraform.tfvars` from the example:

```bash
cd deployments/terraform/environments/eks-live
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — add your GHCR PAT
```

## Usage

```bash
make eks-up          # Create cluster + deploy (~15 min)
make eks-status      # Show pods, services, ingress
make eks-verify      # Health checks against ALB
make eks-logs        # All logs
make eks-logs SERVICE=api   # API logs only
make eks-deploy      # Helm upgrade (no infra changes)
make eks-down        # Destroy everything
```

## Cost

| Resource | Monthly (on-demand) |
|----------|---------------------|
| EKS control plane | ~$73 |
| t3.large x2 | ~$120 |
| NAT gateway | ~$32 |
| ALB | ~$16 + traffic |
| EBS (30GB gp3) | ~$5 |
| **Total** | **~$150-250** |

`make eks-down` destroys everything — $0 when not running.

## Architecture

```
Internet → ALB → API pod → PostgreSQL pod (PVC)
                         → Valkey pod
                         → MinIO pod (PVC)
                         → Vault pod
                UI pod (ClusterIP — access via port-forward)
```

Private subnets for nodes, public subnets for ALB. NAT gateway for outbound traffic.

**UI access:** The UI runs as a ClusterIP service (no external ingress). Access via:
```bash
kubectl port-forward svc/analysi-analysi-ui 8080:80
# Then open http://localhost:8080
```
