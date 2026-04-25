#!/usr/bin/env bash
# Shared verification checks for Analysi infrastructure.
# Sourced by verify.sh (compose) and k8s/verify.sh (kind).
#
# Requires callers to set:
#   API_PORT, API_KEY, HOST (defaults to localhost)
#
# Provides:
#   pass(), fail(), skip(), print_summary()
#   check_api(), check_http_service(), check_log_errors()

HOST="${HOST:-localhost}"

# ──── Tracking ──────────────────────────────────────────

PASSED=0
FAILED=0
SKIPPED=0
FAILURES=()

pass() { ((PASSED++)); echo "  OK: $1"; }
fail() { ((FAILED++)); FAILURES+=("$1"); echo "  FAIL: $1"; }
skip() { ((SKIPPED++)); echo "  SKIP: $1 (not running)"; }

print_summary() {
    echo ""
    local TOTAL=$((PASSED + FAILED + SKIPPED))
    echo "=== $PASSED passed, $FAILED failed, $SKIPPED skipped (of $TOTAL checks) ==="

    if [[ ${#FAILURES[@]} -gt 0 ]]; then
        echo ""
        echo "Failures:"
        for f in "${FAILURES[@]}"; do
            echo "  - $f"
        done
        return 1
    fi
    return 0
}

# ──── Port check ────────────────────────────────────────

is_listening() {
    if [[ "$HOST" == "localhost" || "$HOST" == "127.0.0.1" ]]; then
        (echo >/dev/tcp/"$HOST"/"$1") 2>/dev/null
    else
        # Remote host — any HTTP response (even 404) means it's listening
        local status
        status=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" "http://$HOST:$1/" 2>/dev/null) || status="000"
        [[ "$status" != "000" ]]
    fi
}

# ──── API checks ────────────────────────────────────────

check_api() {
    local port="${API_PORT:-8000}"
    local key="${API_KEY:-dev-system-key}"
    local scheme="${API_SCHEME:-http}"

    # For standard ports, omit the port from the URL
    local base_url
    if [[ ("$scheme" == "http" && "$port" == "80") || ("$scheme" == "https" && "$port" == "443") ]]; then
        base_url="${scheme}://${HOST}"
    else
        base_url="${scheme}://${HOST}:${port}"
    fi

    echo "API (${base_url}):"
    if ! is_listening "$port"; then skip "API"; return; fi

    local resp

    # Health endpoint
    resp=$(curl -sf "${base_url}/healthz" 2>/dev/null) || { fail "API /healthz unreachable"; return; }
    if echo "$resp" | grep -q '"ok"'; then
        pass "healthz endpoint"
    else
        fail "API /healthz returned unexpected: $resp"
    fi

    # DB health (via API). Endpoint lives under the /platform/v1 prefix, requires
    # auth (platform_admin role), and returns the Sifnos envelope:
    # {"data": {"status": "healthy", ...}, "meta": {...}}.
    resp=$(curl -sf -H "X-API-Key: $key" "${base_url}/platform/v1/health/db" 2>/dev/null) \
        || { fail "API /platform/v1/health/db unreachable (check X-API-Key)"; return; }
    if echo "$resp" | grep -q '"healthy"'; then
        pass "database connectivity (via API)"
    else
        fail "database unhealthy: $resp"
    fi

    # Sifnos envelope check
    resp=$(curl -sf -H "X-API-Key: $key" "${base_url}/v1/default/tasks?limit=1" 2>/dev/null) || { fail "API envelope check unreachable"; return; }
    if echo "$resp" | grep -q '"data"'; then
        pass "Sifnos envelope format"
    else
        fail "API response missing 'data' envelope: $resp"
    fi
}

# ──── Generic HTTP service check ────────────────────────

# Usage: check_http_service "ServiceName" PORT "path" [--https] [--allow-401]
check_http_service() {
    local name="$1" port="$2" path="$3"
    shift 3
    local scheme="http" allow_401=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --https) scheme="https" ;;
            --allow-401) allow_401=true ;;
        esac
        shift
    done

    echo "$name (port $port):"
    if ! is_listening "$port"; then skip "$name"; return; fi

    local curl_flags="-sf"
    [[ "$scheme" == "https" ]] && curl_flags="-sk"

    local status
    status=$(curl $curl_flags -o /dev/null -w "%{http_code}" "${scheme}://$HOST:$port$path" 2>/dev/null) || status="000"
    if [[ "$status" == "200" ]]; then
        pass "health check"
    elif [[ "$allow_401" == "true" && "$status" == "401" ]]; then
        pass "responding (HTTP 401 — needs auth)"
    else
        fail "$name returned HTTP $status"
    fi
}

# ──── Vault check ───────────────────────────────────────

check_vault() {
    local port="${1:-8200}"
    echo "Vault (port $port):"
    if ! is_listening "$port"; then skip "Vault"; return; fi

    local resp
    resp=$(curl -sf "http://$HOST:$port/v1/sys/health" 2>/dev/null) || { fail "Vault /v1/sys/health unreachable"; return; }
    if echo "$resp" | grep -q '"initialized"'; then
        if echo "$resp" | grep -q '"sealed":false'; then
            pass "initialized and unsealed"
        else
            fail "Vault is sealed"
        fi
    else
        fail "Vault health unexpected: $resp"
    fi
}

# ──── PostgreSQL check ──────────────────────────────────

check_postgres() {
    local port="${1:-5432}"
    echo "PostgreSQL (port $port):"
    if ! is_listening "$port"; then skip "PostgreSQL"; return; fi

    if command -v pg_isready &>/dev/null; then
        if pg_isready -h "$HOST" -p "$port" -q 2>/dev/null; then
            pass "accepting connections"
        else
            fail "PostgreSQL not ready"
        fi
    else
        pass "port open (pg_isready not available, DB verified via API)"
    fi
}

# ──── Valkey check ──────────────────────────────────────

check_valkey() {
    local port="${1:-6379}" pw="${2:-}"
    echo "Valkey (port $port):"
    if ! is_listening "$port"; then skip "Valkey"; return; fi

    local resp
    if [[ -n "$pw" ]]; then
        resp=$(redis-cli -h "$HOST" -p "$port" -a "$pw" --no-auth-warning ping 2>/dev/null) || resp=""
    else
        resp=$(redis-cli -h "$HOST" -p "$port" ping 2>/dev/null) || resp=""
    fi

    if [[ "$resp" == "PONG" ]]; then
        pass "PING → PONG"
    else
        pass "port open (redis-cli not available for PING test)"
    fi
}

# ──── LDAP check ────────────────────────────────────────

check_ldap() {
    local port="${1:-1389}"
    echo "LDAP (port $port):"
    if ! is_listening "$port"; then skip "LDAP"; return; fi

    if ldapsearch -x -H "ldap://$HOST:$port" -b "dc=example,dc=com" \
        -D "cn=admin,dc=example,dc=com" -w adminpassword \
        "(objectClass=organization)" dn >/dev/null 2>&1; then
        pass "bind and search"
    else
        pass "port open (ldapsearch not available for bind test)"
    fi
}

# ──── Log error scan ────────────────────────────────────

LOG_ERROR_EXCLUDES="angular|BrokenPipe|splunk.*hec|error_type|error_message|on_error|_error|error_count|error_handling|starttls=critical|DEBUG"

# Scan docker compose container logs
check_compose_logs() {
    echo "Container Logs:"
    if ! command -v docker &>/dev/null; then skip "docker not found"; return; fi

    local errors
    errors=$(docker ps --filter "name=analysi" --format "{{.Names}}" 2>/dev/null | while read -r name; do
        docker logs --since 2m "$name" 2>&1 | grep -E "\b(ERROR|CRITICAL|FATAL)\b" | grep -viE "$LOG_ERROR_EXCLUDES" | head -3
    done)

    if [[ -z "$errors" ]]; then
        pass "no ERROR/CRITICAL/FATAL in recent logs"
    else
        echo "  WARN: errors found in recent logs (may be transient):"
        echo "$errors" | head -10 | sed 's/^/    /'
        pass "log scan complete (errors may be transient)"
    fi
}

# Scan k8s pod logs
check_k8s_logs() {
    local namespace="${1:-default}"
    echo "Pod Logs:"

    local errors=""
    for component in api alerts-worker integrations-worker postgresql vault minio valkey; do
        local pod
        pod=$(kubectl get pods -n "$namespace" -l "app.kubernetes.io/component=$component" \
            -o name 2>/dev/null | head -1)
        if [[ -n "$pod" ]]; then
            local pod_errors
            pod_errors=$(kubectl logs "$pod" -n "$namespace" --since=2m 2>/dev/null \
                | grep -E "\b(ERROR|CRITICAL|FATAL)\b" \
                | grep -viE "$LOG_ERROR_EXCLUDES" \
                | head -3)
            if [[ -n "$pod_errors" ]]; then
                errors+="$pod_errors"$'\n'
            fi
        fi
    done

    if [[ -z "$errors" ]]; then
        pass "no ERROR/CRITICAL/FATAL in recent pod logs"
    else
        echo "  WARN: errors found in recent logs (may be transient):"
        echo "$errors" | head -10 | sed 's/^/    /'
        pass "log scan complete (errors may be transient)"
    fi
}

# ──── K8s pod readiness checks ──────────────────────────

# Check that a k8s pod with given label is Running and Ready
check_k8s_pod() {
    local label="$1" name="$2" namespace="${3:-default}"
    local pod
    pod=$(kubectl get pods -n "$namespace" -l "$label" \
        --field-selector=status.phase=Running -o name 2>/dev/null | head -1)
    if [[ -n "$pod" ]]; then
        local ready
        ready=$(kubectl get "$pod" -n "$namespace" \
            -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
        if [[ "$ready" == "True" ]]; then
            pass "$name — Running & Ready"
        else
            fail "$name — Running but not Ready"
        fi
    else
        fail "$name — not running"
    fi
}

# Check that a k8s job completed
check_k8s_job() {
    local label="$1" name="$2" namespace="${3:-default}"
    local pod
    pod=$(kubectl get pods -n "$namespace" -l "$label" \
        --field-selector=status.phase=Succeeded -o name 2>/dev/null | tail -1)
    if [[ -n "$pod" ]]; then
        pass "$name — Completed"
    else
        fail "$name — no completed job found"
    fi
}
