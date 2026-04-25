#!/usr/bin/env bash
# Scan Kubernetes pod logs for error severity levels and produce a summary report.
# Usage: check-pod-log-health.sh [output-dir]
#
# Scans all pods in the default namespace for FATAL, ERROR, and WARNING messages.
# Produces a markdown report and exits non-zero if any FATAL messages are found.
#
# The patterns are intentionally broad but exclude common false positives
# (e.g., log level configuration lines, health check paths, harmless warnings).
set -euo pipefail

OUTPUT_DIR="${1:-k8s-debug-logs}"
mkdir -p "$OUTPUT_DIR"

REPORT="$OUTPUT_DIR/log-health-report.md"

# Counters
declare -A FATAL_COUNTS
declare -A ERROR_COUNTS
declare -A WARNING_COUNTS
TOTAL_FATAL=0
TOTAL_ERROR=0
TOTAL_WARNING=0

# Patterns to EXCLUDE from counts (false positives)
# - Log level config lines (e.g., "level=ERROR" in config)
# - Health check endpoints in access logs
# - "error_page" nginx config directives
# - Vault seal status messages (expected on startup)
# - Python deprecation warnings from dependencies
EXCLUDE_PATTERN='(log_level|log\.level|level.*=.*ERROR|health|readiness|liveness|error_page|"GET /health"|seal_status|DeprecationWarning|PendingDeprecationWarning|warnings\.warn|connection to client lost)'

echo "Scanning pod logs for error patterns..."
echo ""

# Get all pods in default namespace
PODS=$(kubectl get pods -n default -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")

if [ -z "$PODS" ]; then
    echo "No pods found in default namespace"
    echo "# Log Health Report" > "$REPORT"
    echo "" >> "$REPORT"
    echo "No pods found in default namespace." >> "$REPORT"
    exit 0
fi

for pod in $PODS; do
    # Get all container names in this pod
    CONTAINERS=$(kubectl get pod "$pod" -n default -o jsonpath='{.spec.containers[*].name}' 2>/dev/null || echo "")
    INIT_CONTAINERS=$(kubectl get pod "$pod" -n default -o jsonpath='{.spec.initContainers[*].name}' 2>/dev/null || echo "")

    for container in $CONTAINERS $INIT_CONTAINERS; do
        # Fetch logs (tail last 500 lines to keep it bounded)
        LOGS=$(kubectl logs -n default "$pod" -c "$container" --tail=500 2>/dev/null || echo "")

        if [ -z "$LOGS" ]; then
            continue
        fi

        LABEL="${pod}/${container}"

        # Count FATAL (case-insensitive, word boundary)
        FATAL_COUNT=$(echo "$LOGS" | grep -icE '\bFATAL\b' || true)
        FATAL_FP=$(echo "$LOGS" | grep -iE '\bFATAL\b' | grep -icE "$EXCLUDE_PATTERN" || true)
        FATAL_COUNT=$(( ${FATAL_COUNT:-0} - ${FATAL_FP:-0} ))
        if [ "$FATAL_COUNT" -lt 0 ]; then FATAL_COUNT=0; fi

        # Count ERROR (case-insensitive, word boundary)
        ERROR_COUNT=$(echo "$LOGS" | grep -icE '\bERROR\b' || true)
        ERROR_FP=$(echo "$LOGS" | grep -iE '\bERROR\b' | grep -icE "$EXCLUDE_PATTERN" || true)
        ERROR_COUNT=$(( ${ERROR_COUNT:-0} - ${ERROR_FP:-0} ))
        if [ "$ERROR_COUNT" -lt 0 ]; then ERROR_COUNT=0; fi

        # Count WARNING/WARN (case-insensitive, word boundary)
        WARNING_COUNT=$(echo "$LOGS" | grep -icE '\b(WARNING|WARN)\b' || true)
        WARNING_FP=$(echo "$LOGS" | grep -iE '\b(WARNING|WARN)\b' | grep -icE "$EXCLUDE_PATTERN" || true)
        WARNING_COUNT=$(( ${WARNING_COUNT:-0} - ${WARNING_FP:-0} ))
        if [ "$WARNING_COUNT" -lt 0 ]; then WARNING_COUNT=0; fi

        FATAL_COUNTS[$LABEL]=$FATAL_COUNT
        ERROR_COUNTS[$LABEL]=$ERROR_COUNT
        WARNING_COUNTS[$LABEL]=$WARNING_COUNT

        TOTAL_FATAL=$((TOTAL_FATAL + FATAL_COUNT))
        TOTAL_ERROR=$((TOTAL_ERROR + ERROR_COUNT))
        TOTAL_WARNING=$((TOTAL_WARNING + WARNING_COUNT))

        # Save FATAL and ERROR lines to separate files for review
        if [ "$FATAL_COUNT" -gt 0 ]; then
            echo "$LOGS" | grep -iE '\bFATAL\b' | grep -ivE "$EXCLUDE_PATTERN" \
                > "$OUTPUT_DIR/fatal-${pod}-${container}.txt" 2>/dev/null || true
        fi
        if [ "$ERROR_COUNT" -gt 0 ]; then
            echo "$LOGS" | grep -iE '\bERROR\b' | grep -ivE "$EXCLUDE_PATTERN" \
                > "$OUTPUT_DIR/errors-${pod}-${container}.txt" 2>/dev/null || true
        fi
    done
done

# Collect all unique container labels for iteration
# shellcheck disable=SC2207
ALL_LABELS=($(printf '%s\n' "${!FATAL_COUNTS[@]}" "${!ERROR_COUNTS[@]}" "${!WARNING_COUNTS[@]}" | sort -u))

# Generate report
{
    echo "# Log Health Report"
    echo ""
    echo "## Summary"
    echo ""
    echo "| Level | Count |"
    echo "|-------|-------|"
    echo "| FATAL | $TOTAL_FATAL |"
    echo "| ERROR | $TOTAL_ERROR |"
    echo "| WARNING | $TOTAL_WARNING |"
    echo ""

    if [ "${#ALL_LABELS[@]}" -gt 0 ]; then
        HAS_ISSUES=false
        for LABEL in "${ALL_LABELS[@]}"; do
            F=${FATAL_COUNTS[$LABEL]:-0}
            E=${ERROR_COUNTS[$LABEL]:-0}
            W=${WARNING_COUNTS[$LABEL]:-0}
            if [ "$F" -gt 0 ] || [ "$E" -gt 0 ] || [ "$W" -gt 0 ]; then
                HAS_ISSUES=true
                break
            fi
        done

        if [ "$HAS_ISSUES" = true ]; then
            echo "## Per-Container Breakdown"
            echo ""
            echo "| Container | FATAL | ERROR | WARNING |"
            echo "|-----------|-------|-------|---------|"
            for LABEL in "${ALL_LABELS[@]}"; do
                F=${FATAL_COUNTS[$LABEL]:-0}
                E=${ERROR_COUNTS[$LABEL]:-0}
                W=${WARNING_COUNTS[$LABEL]:-0}
                if [ "$F" -gt 0 ] || [ "$E" -gt 0 ] || [ "$W" -gt 0 ]; then
                    echo "| $LABEL | $F | $E | $W |"
                fi
            done
            echo ""
        fi
    fi

    if [ "$TOTAL_FATAL" -gt 0 ]; then
        echo "## FATAL Log Lines"
        echo ""
        for f in "$OUTPUT_DIR"/fatal-*.txt; do
            [ -f "$f" ] || continue
            BASENAME=$(basename "$f" .txt)
            echo "### ${BASENAME#fatal-}"
            echo '```'
            head -20 "$f"
            TOTAL_LINES=$(wc -l < "$f")
            if [ "$TOTAL_LINES" -gt 20 ]; then
                echo "... ($TOTAL_LINES total lines, showing first 20)"
            fi
            echo '```'
            echo ""
        done
    fi

    if [ "$TOTAL_ERROR" -gt 0 ]; then
        echo "## ERROR Log Lines (first 10 per container)"
        echo ""
        for f in "$OUTPUT_DIR"/errors-*.txt; do
            [ -f "$f" ] || continue
            BASENAME=$(basename "$f" .txt)
            echo "### ${BASENAME#errors-}"
            echo '```'
            head -10 "$f"
            TOTAL_LINES=$(wc -l < "$f")
            if [ "$TOTAL_LINES" -gt 10 ]; then
                echo "... ($TOTAL_LINES total lines, showing first 10)"
            fi
            echo '```'
            echo ""
        done
    fi
} > "$REPORT"

# Print summary to stdout
echo "========================================="
echo "  Log Health Report"
echo "========================================="
echo "  FATAL:   $TOTAL_FATAL"
echo "  ERROR:   $TOTAL_ERROR"
echo "  WARNING: $TOTAL_WARNING"
echo "========================================="
echo ""

# Print per-container details if any issues found
if [ "$TOTAL_FATAL" -gt 0 ] || [ "$TOTAL_ERROR" -gt 0 ]; then
    for LABEL in "${ALL_LABELS[@]}"; do
        F=${FATAL_COUNTS[$LABEL]:-0}
        E=${ERROR_COUNTS[$LABEL]:-0}
        W=${WARNING_COUNTS[$LABEL]:-0}
        if [ "$F" -gt 0 ] || [ "$E" -gt 0 ]; then
            echo "  $LABEL: FATAL=$F ERROR=$E WARNING=$W"
        fi
    done
    echo ""
fi

echo "Full report: $REPORT"

# Fail on FATAL
if [ "$TOTAL_FATAL" -gt 0 ]; then
    echo ""
    echo "::error::$TOTAL_FATAL FATAL message(s) found in pod logs"
    exit 1
fi

echo ""
echo "No FATAL messages found. Pod logs look healthy."
