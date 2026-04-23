#!/usr/bin/env bash
# Infrastructure verification for Analysi — Kubernetes (kind) mode.
#
# Checks pod readiness, API health, and recent log errors.
# Exit code 0 = all checks pass, non-zero = at least one failure.
#
# Usage:
#     ./scripts/k8s/verify.sh
#     make k8s-verify
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/../smoke_tests/checks.sh"
source "$SCRIPT_DIR/worktree-ports.sh"

# Worktree-aware cluster name (same logic as local.sh)
if [ "$(git -C "$REPO_ROOT" rev-parse --git-dir 2>/dev/null)" != "$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null)" ] 2>/dev/null; then
    WORKTREE_SLUG=$(basename "$REPO_ROOT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | cut -c1-20)
    CLUSTER_NAME="analysi-${WORKTREE_SLUG}"
    SLOT=$(get_worktree_slot "$CLUSTER_NAME")
    ports_for_slot "$SLOT"
    API_PORT="$API_HOST_PORT"
else
    CLUSTER_NAME="analysi"
    KIND_CONFIG="$REPO_ROOT/deployments/k8s/kind-config.yaml"
    API_PORT=$(yq '.nodes[0].extraPortMappings[] | select(.containerPort == 30080) | .hostPort' "$KIND_CONFIG")
fi

NAMESPACE="default"
# Use the owner key because platform/v1/health/db is platform_admin-only.
# Overridable from the environment for CI that provisions a different key.
API_KEY="${ANALYSI_OWNER_API_KEY:-dev-owner-api-key}"

# ──── Cluster check ─────────────────────────────────────

echo "=== Analysi Infrastructure Verification (K8s) ==="
echo ""

if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    fail "kind cluster '$CLUSTER_NAME' not found"
    print_summary
    exit $?
fi
kubectl config use-context "kind-${CLUSTER_NAME}" &>/dev/null

# ──── Pod health ────────────────────────────────────────

echo "Pods:"
check_k8s_pod "app.kubernetes.io/component=api" "api" "$NAMESPACE"
check_k8s_pod "app.kubernetes.io/component=alerts-worker" "alerts-worker" "$NAMESPACE"
check_k8s_pod "app.kubernetes.io/component=integrations-worker" "integrations-worker" "$NAMESPACE"
check_k8s_pod "app.kubernetes.io/component=postgresql" "postgresql" "$NAMESPACE"
check_k8s_pod "app.kubernetes.io/component=valkey" "valkey" "$NAMESPACE"
check_k8s_job "app.kubernetes.io/component=flyway" "flyway" "$NAMESPACE"

echo ""

# ──── API checks (shared with compose) ──────────────────

check_api

echo ""

# ──── Log scan ──────────────────────────────────────────

check_k8s_logs "$NAMESPACE"

# ──── Summary ───────────────────────────────────────────

print_summary
exit $?
