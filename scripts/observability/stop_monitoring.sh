#!/bin/bash

# Stop PostgreSQL Monitoring Stack

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🛑 Stopping PostgreSQL monitoring stack..."

cd "$PROJECT_ROOT"
docker compose --env-file "$PROJECT_ROOT/.env" \
    -f deployments/compose/core.yml \
    -f deployments/compose/deps.yml \
    -f deployments/compose/observability.yml \
    stop pgadmin postgres-exporter prometheus grafana
docker compose --env-file "$PROJECT_ROOT/.env" \
    -f deployments/compose/core.yml \
    -f deployments/compose/deps.yml \
    -f deployments/compose/observability.yml \
    rm -f pgadmin postgres-exporter prometheus grafana

echo "✅ Monitoring stack stopped!"
