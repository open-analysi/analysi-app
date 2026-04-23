#!/usr/bin/env bash
# Infrastructure verification for Analysi — Docker Compose mode.
#
# Auto-detects which services are running and checks each one.
# Exit code 0 = all checks pass, non-zero = at least one failure.
#
# Usage:
#     ./scripts/smoke_tests/verify.sh
#     make verify
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/checks.sh"

# ──── Configuration — read ports from .env ──────────────

ENV_FILE="${ENV_FILE:-.env}"
if [[ -f "$ENV_FILE" ]]; then
    eval "$(grep -E '^(API_EXTERNAL_PORT|POSTGRES_EXTERNAL_PORT|VALKEY_EXTERNAL_PORT|VALKEY_PASSWORD|VAULT_EXTERNAL_PORT|KEYCLOAK_EXTERNAL_PORT|MINIO_EXTERNAL_PORT|SPLUNK_EXTERNAL_PORT|ECHO_SERVER_EXTERNAL_PORT|LDAP_EXTERNAL_PORT|GRAFANA_EXTERNAL_PORT|PROMETHEUS_EXTERNAL_PORT|ANALYSI_ADMIN_API_KEY)=' "$ENV_FILE")"
fi

API_PORT="${API_EXTERNAL_PORT:-8001}"
API_KEY="${ANALYSI_ADMIN_API_KEY:-dev-admin-api-key}"

# ──── Main ──────────────────────────────────────────────

echo "=== Analysi Infrastructure Verification (Compose) ==="
echo ""

# Layer 1+2: Core Product + Dependencies
check_api
check_postgres "${POSTGRES_EXTERNAL_PORT:-5434}"
check_valkey "${VALKEY_EXTERNAL_PORT:-6380}" "${VALKEY_PASSWORD:-}"
check_vault "${VAULT_EXTERNAL_PORT:-8200}"
check_http_service "Keycloak" "${KEYCLOAK_EXTERNAL_PORT:-8080}" "/realms/analysi"
check_http_service "MinIO" "${MINIO_EXTERNAL_PORT:-9000}" "/minio/health/live"

echo ""

# Layer 3: Integrations (auto-detected)
check_http_service "Splunk" "${SPLUNK_EXTERNAL_PORT:-8089}" "/services/server/info" --https --allow-401
check_http_service "Echo Server" "${ECHO_SERVER_EXTERNAL_PORT:-8003}" "/__health"
check_ldap "${LDAP_EXTERNAL_PORT:-1389}"

echo ""

# Layer 4: Observability (auto-detected)
check_http_service "Grafana" "${GRAFANA_EXTERNAL_PORT:-3000}" "/api/health"
check_http_service "Prometheus" "${PROMETHEUS_EXTERNAL_PORT:-9090}" "/-/healthy"

echo ""

# Log scan
check_compose_logs

# Summary
print_summary
exit $?
