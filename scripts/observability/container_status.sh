#!/usr/bin/env bash

# Analysi Container Status Display
# Shows container status with fancy formatting, colors, and resource usage

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                    Analysi Container Status                     ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

# Container status with color coding
printf "%-35s %-25s %-30s\n" "CONTAINER" "STATUS" "PORTS"
printf "%-35s %-25s %-30s\n" "─────────" "──────" "─────"
docker ps --filter "name=analysi-" --format '{{.Names}}|{{.Status}}|{{.Ports}}' | \
    sort | while IFS='|' read -r name cstatus ports; do
        if echo "$cstatus" | grep -q "Up"; then
            printf "%-35s %-25s %-30s\n" "$name" "✅ $cstatus" "$ports"
        elif echo "$cstatus" | grep -q "Exit"; then
            printf "%-35s %-25s %-30s\n" "$name" "❌ $cstatus" "$ports"
        else
            printf "%-35s %-25s %-30s\n" "$name" "⚠️  $cstatus" "$ports"
        fi
    done

echo ""
echo "──────────────────────────────────────────────────────────────────────"
echo "📊 Resource Usage:"

# Resource usage statistics — filter to project containers by COMPOSE_PROJECT_NAME
PROJECT_PREFIX="${COMPOSE_PROJECT_NAME:-analysi}-"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | \
    awk -v prefix="$PROJECT_PREFIX" 'BEGIN {
        printf "%-35s %-15s %-25s\n", "CONTAINER", "CPU %", "MEMORY";
        printf "%-35s %-15s %-25s\n", "─────────", "─────", "──────";
    }
    NR>1 && index($1, prefix) == 1 {
        printf "%-35s %-15s %-25s\n", $1, $2, $3" "$4" "$5;
    }'

echo ""
echo "──────────────────────────────────────────────────────────────────────"
echo "📝 Quick Commands:"
echo "  • View logs:     make logs SERVICE=<name>  (api, alerts-worker, integrations-worker, postgres)"
echo "  • Restart:       make restart SERVICE=<name>"
echo "  • Rebuild:       make rebuild SERVICE=<name>"
echo "  • All logs:      make logs"
