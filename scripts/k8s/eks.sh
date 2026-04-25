#!/usr/bin/env bash
# EKS management script — same subcommand pattern as local.sh
#
# Usage:
#   bash scripts/k8s/eks.sh up        # Create EKS cluster + deploy
#   bash scripts/k8s/eks.sh down      # Destroy EKS cluster
#   bash scripts/k8s/eks.sh deploy    # Helm upgrade only (no infra changes)
#   bash scripts/k8s/eks.sh status    # Show pod/service/ingress status
#   bash scripts/k8s/eks.sh verify    # Health checks against ALB
#   bash scripts/k8s/eks.sh logs      # Tail logs (optional: component name)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="${REPO_ROOT}/deployments/terraform/environments/eks-live"
REGION="${AWS_REGION:-us-east-1}"
NAMESPACE="${NAMESPACE:-analysi}"

# Read cluster name from terraform output if available, fall back to env var / default
if [ -z "${CLUSTER_NAME:-}" ]; then
    CLUSTER_NAME=$(cd "${TF_DIR}" && terraform output -raw cluster_name 2>/dev/null) || CLUSTER_NAME="analysi-eks-live"
fi

# ──── Helpers ─────────────────────────────────

check_prerequisites() {
    local missing=()
    for cmd in aws terraform kubectl helm; do
        command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "ERROR: Missing required tools: ${missing[*]}"
        echo "Install them before continuing."
        exit 1
    fi
}

configure_kubeconfig() {
    echo "==> Configuring kubectl for ${CLUSTER_NAME}..."
    # Errors suppressed: may fail if cluster doesn't exist yet (e.g. during first 'up')
    aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${REGION}" 2>/dev/null || true
}

get_api_url() {
    kubectl -n "${NAMESPACE}" get ingress -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo ""
}

get_api_protocol() {
    # HTTPS when ACM cert is configured, HTTP otherwise (demo with CIDR restriction)
    local cert
    cert=$(kubectl -n "${NAMESPACE}" get ingress -o jsonpath='{.items[0].metadata.annotations.alb\.ingress\.kubernetes\.io/certificate-arn}' 2>/dev/null) || cert=""
    if [ -n "${cert}" ]; then
        echo "https"
    else
        echo "http"
    fi
}

# ──── Commands ────────────────────────────────

cmd_up() {
    check_prerequisites

    # GHCR PAT must be set as env var (not stored in files)
    if [ -z "${TF_VAR_ghcr_pat:-}" ]; then
        echo "ERROR: TF_VAR_ghcr_pat is not set."
        echo "Export it before running: export TF_VAR_ghcr_pat=ghp_..."
        exit 1
    fi

    echo "==> Creating EKS cluster (this takes ~15 minutes)..."

    cd "${TF_DIR}"
    terraform init
    terraform apply -auto-approve

    configure_kubeconfig

    echo ""
    echo "==> Waiting for pods to be ready..."
    kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/instance=analysi --timeout=300s 2>/dev/null || true

    cmd_status
    echo ""
    terraform output -raw deployment_summary 2>/dev/null || true
}

cmd_down() {
    check_prerequisites
    echo ""
    echo "⚠️  This will DESTROY the EKS cluster and ALL data."
    echo "    Cluster: ${CLUSTER_NAME}"
    echo "    Region:  ${REGION}"
    echo ""
    read -r -p "Type 'destroy' to confirm: " confirm
    if [ "${confirm}" != "destroy" ]; then
        echo "Cancelled."
        exit 0
    fi

    # Delete ingress first so the ALB controller can clean up the ALB
    # before Terraform kills the controller pod. Without this, the ALB
    # and its ENIs orphan, blocking VPC/IGW deletion for 15+ minutes.
    echo "==> Cleaning up ALB ingress..."
    kubectl delete ingress --all -n "${NAMESPACE}" --timeout=120s 2>/dev/null || true
    echo "    Waiting 30s for ALB to drain and ENIs to detach..."
    sleep 30

    cd "${TF_DIR}"
    terraform destroy -auto-approve

    echo "==> EKS cluster destroyed."
}

cmd_deploy() {
    check_prerequisites
    configure_kubeconfig

    echo "==> Upgrading Helm release..."
    cd "${TF_DIR}"
    # -target: only update the Helm release, skip infra (VPC, EKS, IAM).
    # This is intentional for fast deploys when infra hasn't changed.
    terraform apply -target=helm_release.analysi -auto-approve

    echo "==> Waiting for rollout..."
    kubectl -n "${NAMESPACE}" wait --for=condition=ready pod -l app.kubernetes.io/instance=analysi --timeout=300s 2>/dev/null || true

    cmd_status
}

cmd_status() {
    configure_kubeconfig

    echo ""
    echo "──── Pods ────────────────────────────────"
    kubectl -n "${NAMESPACE}" get pods -o wide 2>/dev/null || echo "No pods found"
    echo ""
    echo "──── Services ────────────────────────────"
    kubectl -n "${NAMESPACE}" get svc 2>/dev/null || echo "No services found"
    echo ""
    echo "──── Ingress ─────────────────────────────"
    kubectl -n "${NAMESPACE}" get ingress 2>/dev/null || echo "No ingress found"
    echo ""

    local url proto
    url=$(get_api_url)
    if [ -n "${url}" ]; then
        proto=$(get_api_protocol)
        echo "API URL: ${proto}://${url}"
    fi
}

cmd_verify() {
    # Disable set -e: checks.sh uses grep which returns 1 on no matches
    set +e
    configure_kubeconfig

    source "${REPO_ROOT}/scripts/smoke_tests/checks.sh"

    local url proto
    url=$(get_api_url)
    if [ -z "${url}" ]; then
        fail "No ALB URL found — is the ingress ready?"
        kubectl -n "${NAMESPACE}" get ingress
        print_summary
        exit $?
    fi
    proto=$(get_api_protocol)

    echo "=== Analysi Infrastructure Verification (EKS) ==="
    echo "    Endpoint: ${proto}://${url}"
    echo ""

    # ── Pod readiness ──────────────────────────────
    echo "Pods:"
    check_k8s_pod "app.kubernetes.io/component=api" "api" "${NAMESPACE}"
    check_k8s_pod "app.kubernetes.io/component=alerts-worker" "alerts-worker" "${NAMESPACE}"
    check_k8s_pod "app.kubernetes.io/component=integrations-worker" "integrations-worker" "${NAMESPACE}"
    check_k8s_pod "app.kubernetes.io/component=postgresql" "postgresql" "${NAMESPACE}"
    check_k8s_pod "app.kubernetes.io/component=valkey" "valkey" "${NAMESPACE}"
    check_k8s_pod "app.kubernetes.io/component=vault" "vault" "${NAMESPACE}"
    check_k8s_pod "app.kubernetes.io/component=minio" "minio" "${NAMESPACE}"
    check_k8s_job "app.kubernetes.io/component=flyway" "flyway" "${NAMESPACE}"
    echo ""

    # ── API checks via ALB ─────────────────────────
    # Override HOST/API_PORT/API_SCHEME so check_api() hits the ALB
    HOST="${url}"
    API_SCHEME="${proto}"
    API_PORT="80"
    if [ "${proto}" = "https" ]; then
        API_PORT="443"
    fi

    # Get admin key from Terraform outputs
    API_KEY=$(cd "${TF_DIR}" && terraform output -raw api_admin_key 2>/dev/null) || API_KEY=""

    check_api
    echo ""

    # ── Log scan ───────────────────────────────────
    check_k8s_logs "${NAMESPACE}"

    # ── Summary ────────────────────────────────────
    print_summary
    exit $?
}

cmd_logs() {
    configure_kubeconfig

    local component="${1:-}"
    if [ -n "${component}" ]; then
        kubectl -n "${NAMESPACE}" logs -l app.kubernetes.io/component="${component}" --tail=100 -f
    else
        kubectl -n "${NAMESPACE}" logs -l app.kubernetes.io/instance=analysi --tail=50 --all-containers
    fi
}

# ──── Dispatch ────────────────────────────────

case "${1:-help}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    deploy)  cmd_deploy ;;
    status)  cmd_status ;;
    verify)  cmd_verify ;;
    logs)    shift; cmd_logs "${1:-}" ;;
    help|*)
        echo "Usage: $0 {up|down|deploy|status|verify|logs [component]}"
        echo ""
        echo "  up      — Create EKS cluster + deploy all services (~15 min)"
        echo "  down    — Destroy EKS cluster (with confirmation)"
        echo "  deploy  — Helm upgrade only (no infra changes)"
        echo "  status  — Show pods, services, ingress"
        echo "  verify  — Health checks against ALB endpoint"
        echo "  logs    — Tail logs (optionally filter by component: api, alerts-worker, etc.)"
        ;;
esac
