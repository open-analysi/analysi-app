#!/bin/bash

# Check PostgreSQL Monitoring Stack Status
# Uses .env file for port configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load environment variables for port configuration (skip problematic lines)
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Load only the monitoring port variables we need
    export $(grep -E "^(POSTGRES_EXPORTER_EXTERNAL_PORT|PROMETHEUS_EXTERNAL_PORT|GRAFANA_EXTERNAL_PORT)=" "$PROJECT_ROOT/.env" | xargs)
fi

echo "📊 PostgreSQL Monitoring Stack Status"
echo "======================================"

cd "$PROJECT_ROOT"
docker compose --env-file "$PROJECT_ROOT/.env" \
    -f deployments/compose/core.yml \
    -f deployments/compose/deps.yml \
    -f deployments/compose/observability.yml \
    ps pgadmin postgres-exporter prometheus grafana

echo ""
echo "🔍 Health Checks:"

# PostgreSQL Exporter health check
echo -n "  PostgreSQL Exporter: "
if curl -s "http://localhost:${POSTGRES_EXPORTER_EXTERNAL_PORT:-9188}/metrics" | grep -q "pg_up 1" 2>/dev/null; then
    echo "✅ Connected to PostgreSQL"
else
    echo "❌ Cannot connect to PostgreSQL"
fi

# Prometheus health check
echo -n "  Prometheus: "
if curl -s "http://localhost:${PROMETHEUS_EXTERNAL_PORT:-9090}/-/healthy" 2>/dev/null | grep -q "Prometheus" 2>/dev/null; then
    echo "✅ Healthy"
else
    echo "❌ Unhealthy or not running"
fi

# Grafana health check
echo -n "  Grafana: "
if curl -s "http://localhost:${GRAFANA_EXTERNAL_PORT:-3000}/api/health" 2>/dev/null | grep -q "ok" 2>/dev/null; then
    echo "✅ Healthy"
else
    echo "❌ Unhealthy or not running"
fi

echo ""
echo "📊 Access URLs (if running):"
echo "   Grafana: http://localhost:${GRAFANA_EXTERNAL_PORT:-3000} (admin/admin)"
echo "   Prometheus: http://localhost:${PROMETHEUS_EXTERNAL_PORT:-9090}"
echo "   PostgreSQL Metrics: http://localhost:${POSTGRES_EXPORTER_EXTERNAL_PORT:-9188}/metrics"
