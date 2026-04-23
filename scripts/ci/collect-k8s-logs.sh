#!/usr/bin/env bash
# Collect Kubernetes logs and events for CI debugging
# Usage: collect-k8s-logs.sh [output-dir]
#
# Gathers pod logs, descriptions, and cluster events into a directory
# that can be uploaded as a GitHub Actions artifact on failure.
set -euo pipefail

OUTPUT_DIR="${1:-k8s-debug-logs}"
mkdir -p "$OUTPUT_DIR"

echo "Collecting k8s debug info into $OUTPUT_DIR/"

# Cluster-wide events
echo "  Gathering events..."
kubectl get events --all-namespaces --sort-by='.lastTimestamp' \
    > "$OUTPUT_DIR/events.txt" 2>&1 || true

# Pod status summary
echo "  Gathering pod status..."
kubectl get pods -A -o wide > "$OUTPUT_DIR/pod-status.txt" 2>&1 || true

# Per-pod logs and describe
echo "  Gathering per-pod logs..."
for pod in $(kubectl get pods -n default -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
    kubectl logs -n default "$pod" --all-containers --tail=200 \
        > "$OUTPUT_DIR/logs-${pod}.txt" 2>&1 || true
    kubectl describe pod -n default "$pod" \
        > "$OUTPUT_DIR/describe-${pod}.txt" 2>&1 || true
done

# Helm release info
echo "  Gathering helm status..."
helm list -A > "$OUTPUT_DIR/helm-list.txt" 2>&1 || true
helm status analysi -n default > "$OUTPUT_DIR/helm-status.txt" 2>&1 || true

# Services and endpoints
echo "  Gathering services..."
kubectl get svc,endpoints -A > "$OUTPUT_DIR/services.txt" 2>&1 || true

echo "Done. Files in $OUTPUT_DIR/:"
ls -la "$OUTPUT_DIR/"
