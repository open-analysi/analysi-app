#!/usr/bin/env bash
# Star all provisioned Grafana dashboards for the admin user.
# Idempotent — re-starring an already-starred dashboard is a no-op.
#
# Usage: star_dashboards.sh
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://localhost:${GRAFANA_EXTERNAL_PORT:-3000}}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASS="${GRAFANA_ADMIN_PASSWORD:-admin}"

echo "Waiting for Grafana at ${GRAFANA_URL}..."
for i in $(seq 1 30); do
    if curl -sf "${GRAFANA_URL}/api/health" > /dev/null 2>&1; then
        echo "Grafana is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Grafana did not become ready in 60s"
        exit 1
    fi
    sleep 2
done

# Fetch all dashboard UIDs and star each one via UID-based API
DASHBOARDS=$(curl -sf -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
    "${GRAFANA_URL}/api/search?type=dash-db" || echo "[]")

echo "$DASHBOARDS" | python3 -c "
import json, sys
for d in json.load(sys.stdin):
    print(d['uid'], d.get('title', 'unknown'))
" | while IFS=' ' read -r DASH_UID DASH_TITLE; do
    HTTP_CODE=$(curl -o /dev/null -w '%{http_code}' -s \
        -u "${GRAFANA_USER}:${GRAFANA_PASS}" \
        -X POST "${GRAFANA_URL}/api/user/stars/dashboard/uid/${DASH_UID}" 2>/dev/null || echo "000")
    echo "  Starred: ${DASH_TITLE} (uid=${DASH_UID}, status=${HTTP_CODE})"
done

echo "All dashboards starred."
