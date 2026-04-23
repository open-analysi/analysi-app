#!/bin/bash

# Start PostgreSQL Monitoring Stack
# Uses .env file for port configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🚀 Starting PostgreSQL monitoring stack..."

# Start monitoring stack
cd "$PROJECT_ROOT"
docker compose --env-file "$PROJECT_ROOT/.env" \
    -f deployments/compose/core.yml \
    -f deployments/compose/deps.yml \
    -f deployments/compose/observability.yml \
    up -d pgadmin postgres-exporter valkey-exporter prometheus grafana

echo "✅ Monitoring stack started!"
echo ""
echo "📊 Access URLs:"
echo "   Grafana: http://localhost:${GRAFANA_EXTERNAL_PORT:-3000} (admin/admin)"
echo "   Prometheus: http://localhost:${PROMETHEUS_EXTERNAL_PORT:-9090}"
echo "   PostgreSQL Metrics: http://localhost:${POSTGRES_EXPORTER_EXTERNAL_PORT:-9188}/metrics"
echo "   Valkey Metrics: http://localhost:${VALKEY_EXPORTER_EXTERNAL_PORT:-9121}/metrics"
echo ""

# Star all dashboards for the admin user
"$SCRIPT_DIR/star_dashboards.sh"

echo "💡 Use 'make monitoring-status' to check health"
