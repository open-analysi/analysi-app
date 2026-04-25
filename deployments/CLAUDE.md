# Deployments — Learnings & Gotchas

Hard-won lessons from building and debugging our deployment infrastructure.

## Environment Files & Secrets

`.env` is **gitignored** — it contains real API keys and must never be committed. For CI or other environments that need a compose-compatible env file, create a purpose-specific variant (e.g., `.env.nightly`) that:
- Is tracked in git
- Contains **no API keys or real secrets** — use empty values or nightly/CI-specific throwaway passwords
- Documents its purpose in a header comment

Existing env files:
| File | Tracked | Purpose |
|------|---------|---------|
| `.env` | No | Local dev (has real API keys) |
| `.env.example` | Yes | Template for new developers |
| `.env.nightly` | Yes | Nightly CI integration tests |
| `.env.test` | Yes | Test runner config |

When adding a new env file: review it for secrets before committing. When a compose service needs env vars, it loads them via `env_file: ../../.env` — so CI workflows must `cp .env.<variant> .env` before running compose.

## Configuration DRY Principle

Avoid hardcoding ports, hostnames, or credentials as raw numbers/strings across files. When a value appears in multiple places (compose file, workflow env vars, test config), it should trace back to a single source — typically an `.env` file or a Helm values file.

**Bad** — same port repeated in 3 files, will drift:
```yaml
# deps.yml
ports: ["5434:5432"]
# workflow
TEST_DB_PORT: "5434"
# test config
db_port = 5434
```

**Better** — workflow comments reference the source, making drift detectable:
```yaml
# workflow
# Must match POSTGRES_EXTERNAL_PORT in .env.nightly
TEST_DB_PORT: "5434"
```

**Best** — value is read from the source at runtime (when feasible):
```bash
source .env.nightly
export TEST_DB_PORT=$POSTGRES_EXTERNAL_PORT
```

Apply this especially to ports, passwords, and bucket names that are shared between compose services and test env vars.

## Terraform

### Never use computed values in `count`
`count = var.some_arn != "" ? 1 : 0` fails when the ARN comes from a module output that doesn't exist yet. Terraform needs to evaluate `count` at plan time.
**Fix**: Use a boolean variable: `count = var.create_thing ? 1 : 0`

### Module circular dependencies
When resource A needs output from module B, and module B needs output from module C, but A lives inside C — move A out of C into the environment's `main.tf` where both outputs are accessible. Example: EBS CSI addon needs IRSA role ARN (from IAM module) but lived inside the EKS module (which the IAM module depends on).

### IRSA over node role
Always prefer IRSA (IAM Roles for Service Accounts) over attaching policies to the node role. Node role permissions are available to every pod on the node. IRSA scopes permissions to a specific ServiceAccount.
Pattern: IAM role with `sts:AssumeRoleWithWebIdentity` trust → scoped to `system:serviceaccount:<namespace>:<sa-name>` → pass ARN via `service_account_role_arn` (addons) or Helm annotation.

### ACM requires a domain you own
ALB HTTPS needs an ACM certificate, which requires a domain. You cannot get a cert for `*.elb.amazonaws.com`. For demos without a domain: use HTTP + `inbound-cidrs` annotation to restrict access by IP.

## Helm

### Secrets via secretKeyRef, not plain values
Dependency pods (PostgreSQL, MinIO, Vault) should read credentials from Kubernetes Secrets via `secretKeyRef`, not from plain `value:` in the manifest. Plain values are visible in `kubectl get deploy -o yaml`.

### Conditional PVC pattern
Use `persistence.enabled` flag: `emptyDir` when false (local/kind), PVC when true (EKS). Keep the PVC resource definition in the same template file, guarded by `{{- if .Values.X.persistence.enabled }}`.

### Ingress host is optional
ALB ingress rules don't need a `host:` field — omitting it creates a wildcard rule that matches the ALB's auto-generated hostname. Make the host conditional: `{{- if .host }}`.

## EKS

### Delete ingress before terraform destroy
When Terraform destroys the Helm release, the ALB controller pod dies before cleaning up the ALB it created. The orphaned ALB leaves ENIs in the VPC, blocking IGW/subnet/VPC deletion for 15+ minutes (or forever). **Fix**: `kubectl delete ingress --all` before `terraform destroy`, then wait ~30s for ENI detach. This is handled automatically in `eks.sh cmd_down()`.

### Sizing (demo)
- 1x t3.large (8GB) fits all pods with ~4GB headroom
- System components (kubelet, kube-proxy, CNI, CSI) reserve ~1GB per node
- Give PostgreSQL extra memory — it benefits most from caching

### Image tagging
Release workflow tags: `latest`, `YYYY-MM-DD`, `sha-<commit>`. Git tag push adds semver (`v1.2.3`). EKS deploys via `image_tag` Terraform variable.

### EBS CSI doesn't create gp3 StorageClass
The EBS CSI addon only creates a `gp2` StorageClass (using the legacy `kubernetes.io/aws-ebs` provisioner). If your PVCs reference `gp3`, you must create the StorageClass yourself with `provisioner: ebs.csi.aws.com`. Without it, PVCs stay Pending forever.

### ALB controller v2.11+ needs DescribeListenerAttributes
ALB controller chart v1.11.0 (controller v2.11) requires `elasticloadbalancing:DescribeListenerAttributes` in the IAM policy. Older policy JSON files from AWS docs may not include it. Symptom: ingress gets no ADDRESS, controller logs show 403 AccessDenied.

### Vault probe timeouts
Vault dev mode on resource-constrained nodes may take >1s to respond to `vault status`. Set `timeoutSeconds: 5` on both readiness and liveness probes. Default 1s causes CrashLoopBackOff.

## Database

### asyncpg SSL via SQLAlchemy
SQLAlchemy's asyncpg dialect ignores `?ssl=disable` in the DATABASE_URL query string. SSL must be controlled via `connect_args={"ssl": True/False}` in `create_async_engine()`. Use a `DATABASE_SSL` setting, not environment name checks.

## Shell Scripts

### `set -e` and arithmetic
`((var++))` returns exit code 1 when var is 0, which kills the script under `set -e`. Use `var=$((var + 1))` instead.

### S3 bucket creation in us-east-1
`aws s3api create-bucket` in us-east-1 must NOT include `--create-bucket-configuration LocationConstraint`. Other regions require it. Always special-case us-east-1.
