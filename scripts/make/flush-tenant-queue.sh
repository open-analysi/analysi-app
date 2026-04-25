#!/bin/bash
# Flush the ARQ/Valkey job queue for a specific tenant.
# Use after manually cleaning a tenant's DB data to stop stale jobs.
# Requires owner-level API key (bulk_operations.delete permission).
#
# Usage: ./scripts/make/flush-tenant-queue.sh [TENANT]

set -e

TENANT="${1:-default}"
API_KEY="${ANALYSI_OWNER_API_KEY:-dev-owner-api-key-change-in-production}"
API_PORT="${BACKEND_API_EXTERNAL_PORT:-8001}"

echo "Flushing Valkey queue for tenant: $TENANT"

curl -s -X DELETE \
    "http://localhost:${API_PORT}/v1/${TENANT}/analysis-queue?mark_alerts_failed=false&abort_in_progress=false" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" | python3 -m json.tool

echo "Queue flush complete for tenant: $TENANT"
