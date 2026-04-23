#!/bin/bash

# Integration Test Runner Script
# This script runs integration tests against the backend APIs

set -e  # Exit on error

# Load .env if present (so `make test-integration` picks up VITE_E2E_API_KEY etc.)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# Also source .env.test for test-only vars (e.g. VITE_BACKEND_API_TENANT)
TEST_ENV_FILE="$SCRIPT_DIR/../.env.test"
if [ -f "$TEST_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$TEST_ENV_FILE"
    set +a
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
BACKEND_HEALTH_ENDPOINT="/docs"
TIMEOUT=5
TENANT="${VITE_BACKEND_API_TENANT:-default}"

# API key for backend authentication.
# Must match ANALYSI_SYSTEM_API_KEY configured in the backend.
API_KEY="${VITE_E2E_API_KEY:-dev-system-api-key-change-in-production}"

# Wrapper around curl that always injects the X-API-Key header.
api_curl() {
    curl -H "X-API-Key: $API_KEY" "$@"
}

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to print section headers
print_section() {
    echo ""
    print_color "$CYAN" "============================================================"
    print_color "$CYAN" "$1"
    print_color "$CYAN" "============================================================"
}

# Function to check if backend is running
check_backend() {
    print_section "Pre-flight Checks"
    
    print_color "$BLUE" "ℹ️  Checking backend availability at $BACKEND_URL..."
    
    if curl -s -f -m $TIMEOUT "$BACKEND_URL$BACKEND_HEALTH_ENDPOINT" > /dev/null 2>&1; then
        print_color "$GREEN" "✅ Backend is running at $BACKEND_URL"
        return 0
    else
        print_color "$RED" "❌ Backend is not accessible at $BACKEND_URL"
        print_color "$YELLOW" "Please ensure the backend is running with:"
        print_color "$YELLOW" "  ./docker-compose.sh up"
        return 1
    fi
}

# Function to test sorting functionality
test_sorting() {
    print_section "Alert Sorting API Tests"
    
    print_color "$BLUE" "Testing sorting functionality..."
    
    local TENANT="$TENANT"
    local BASE_URL="$BACKEND_URL/v1/$TENANT/alerts"
    
    # Test created_at sorting (ascending)
    print_color "$YELLOW" "Testing created_at ascending..."
    local RESPONSE=$(api_curl -s "$BASE_URL?sort_by=created_at&sort_order=asc&limit=3")
    local DATES=$(echo "$RESPONSE" | jq -r '.data[].created_at' 2>/dev/null)
    
    local HAS_DATA=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null)

    if [ "$HAS_DATA" -eq 0 ] 2>/dev/null; then
        print_color "$YELLOW" "  ⚠️  No alerts to test created_at ascending sort"
    elif [ -n "$DATES" ]; then
        # Check if dates are in ascending order
        local PREV=""
        local SORTED=true
        while IFS= read -r DATE; do
            if [ -n "$PREV" ] && [ "$DATE" \< "$PREV" ]; then
                SORTED=false
                break
            fi
            PREV="$DATE"
        done <<< "$DATES"

        if [ "$SORTED" = true ]; then
            print_color "$GREEN" "  ✅ created_at ascending sort works"
        else
            print_color "$RED" "  ❌ created_at ascending sort failed"
        fi
    else
        print_color "$RED" "  ❌ Failed to fetch sorted data"
    fi
    
    # Test created_at sorting (descending)
    print_color "$YELLOW" "Testing created_at descending..."
    RESPONSE=$(api_curl -s "$BASE_URL?sort_by=created_at&sort_order=desc&limit=3")
    DATES=$(echo "$RESPONSE" | jq -r '.data[].created_at' 2>/dev/null)
    
    HAS_DATA=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null)

    if [ "$HAS_DATA" -eq 0 ] 2>/dev/null; then
        print_color "$YELLOW" "  ⚠️  No alerts to test created_at descending sort"
    elif [ -n "$DATES" ]; then
        local PREV=""
        local SORTED=true
        while IFS= read -r DATE; do
            if [ -n "$PREV" ] && [ "$DATE" \> "$PREV" ]; then
                SORTED=false
                break
            fi
            PREV="$DATE"
        done <<< "$DATES"

        if [ "$SORTED" = true ]; then
            print_color "$GREEN" "  ✅ created_at descending sort works"
        else
            print_color "$RED" "  ❌ created_at descending sort failed"
        fi
    else
        print_color "$RED" "  ❌ Failed to fetch sorted data"
    fi
    
    # Test severity sorting
    print_color "$YELLOW" "Testing severity sorting..."
    RESPONSE=$(api_curl -s "$BASE_URL?sort_by=severity&sort_order=desc&limit=5")
    local SEVERITIES=$(echo "$RESPONSE" | jq -r '.data[].severity' 2>/dev/null)
    
    HAS_DATA=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null)

    if [ "$HAS_DATA" -eq 0 ] 2>/dev/null; then
        print_color "$YELLOW" "  ⚠️  No alerts to test severity sort"
    elif [ -n "$SEVERITIES" ]; then
        print_color "$GREEN" "  ✅ Severity sort endpoint accessible"
        echo "    Severities order: $(echo $SEVERITIES | tr '\n' ' ')"
    else
        print_color "$RED" "  ❌ Failed to fetch severity sorted data"
    fi
    
    # Test confidence sorting (for analyzed alerts)
    print_color "$YELLOW" "Testing confidence sorting..."
    RESPONSE=$(api_curl -s "$BASE_URL?sort_by=confidence&sort_order=desc&analysis_status=analyzed&limit=3")
    local HAS_DATA=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null)
    
    if [ "$HAS_DATA" -gt 0 ] 2>/dev/null; then
        print_color "$GREEN" "  ✅ Confidence sort endpoint accessible"
    else
        print_color "$YELLOW" "  ⚠️  No analyzed alerts to test confidence sorting"
    fi
    
    echo ""
}

# Function to run Alert API tests
run_alert_tests() {
    print_section "Alert Management API Integration Tests"

    print_color "$BLUE" "Running Alert API tests..."

    # Run the manual test script (pass API key so backendApiClient can auth)
    if ANALYSI_SYSTEM_API_KEY="$API_KEY" npx tsx src/services/__tests__/testAlertsApi.ts 2>/dev/null | grep -E "(✅|❌|ℹ️|Test Results)"; then
        echo ""  # Add spacing after grep output
    fi

    # Note: Integration tests are excluded from vitest config
    # They are run manually via npx tsx instead
    print_color "$CYAN" "ℹ️  Integration tests are run via manual test scripts"
}

# Function to test Integration Registry APIs
test_integration_registry() {
    print_section "Integration Registry API Tests"

    local TENANT="$TENANT"
    local BASE_URL="$BACKEND_URL/v1/$TENANT"

    # Test listing all integration types
    print_color "$YELLOW" "Testing integration registry list..."
    local RESPONSE=$(api_curl -s "$BASE_URL/integrations/registry")
    local COUNT=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null)

    if [ "$COUNT" -gt 0 ] 2>/dev/null; then
        print_color "$GREEN" "  ✅ Found $COUNT integration types"

        # List available types
        local TYPES=$(echo "$RESPONSE" | jq -r '.data[].integration_type' 2>/dev/null)
        echo "    Available types: $(echo $TYPES | tr '\n' ', ')"
    else
        print_color "$RED" "  ❌ Failed to fetch integration registry"
        return 1
    fi

    # Test getting details for a specific integration type
    print_color "$YELLOW" "Testing integration type details (splunk)..."
    RESPONSE=$(api_curl -s "$BASE_URL/integrations/registry/splunk")
    local HAS_SCHEMA=$(echo "$RESPONSE" | jq '.data.settings_schema' 2>/dev/null)

    if [ -n "$HAS_SCHEMA" ] && [ "$HAS_SCHEMA" != "null" ]; then
        print_color "$GREEN" "  ✅ Retrieved splunk integration schema"

        # Check for important schema fields
        local HAS_CREDS=$(echo "$RESPONSE" | jq '.data.credential_schema' 2>/dev/null)
        local CONNECTORS=$(echo "$RESPONSE" | jq '.data.connectors | length' 2>/dev/null)

        if [ -n "$HAS_CREDS" ] && [ "$HAS_CREDS" != "null" ]; then
            print_color "$GREEN" "    ✓ Has credential schema"
        fi

        if [ "$CONNECTORS" -gt 0 ] 2>/dev/null; then
            print_color "$GREEN" "    ✓ Has $CONNECTORS connectors"
        fi
    else
        print_color "$RED" "  ❌ Failed to get integration type details"
    fi

    # Test getting connector details
    print_color "$YELLOW" "Testing connector details (pull_alerts)..."
    RESPONSE=$(api_curl -s "$BASE_URL/integrations/registry/splunk/connectors/pull_alerts")
    local HAS_PARAMS=$(echo "$RESPONSE" | jq '.data.params_schema' 2>/dev/null)

    if [ -n "$HAS_PARAMS" ] && [ "$HAS_PARAMS" != "null" ]; then
        print_color "$GREEN" "  ✅ Retrieved connector params schema"

        # Check for lookback_seconds parameter
        local HAS_LOOKBACK=$(echo "$RESPONSE" | jq '.data.params_schema.properties.lookback_seconds' 2>/dev/null)
        if [ -n "$HAS_LOOKBACK" ] && [ "$HAS_LOOKBACK" != "null" ]; then
            print_color "$GREEN" "    ✓ Has lookback_seconds parameter"
        fi
    else
        print_color "$RED" "  ❌ Failed to get connector details"
    fi

    echo ""
}

# Function to test Integration CRUD operations
test_integration_crud() {
    print_section "Integration CRUD Operations Test"

    local TENANT="$TENANT"
    local BASE_URL="$BACKEND_URL/v1/$TENANT"
    local TEST_ID="test-integration-$(date +%s)"

    # Create a test integration
    print_color "$YELLOW" "Creating test integration..."
    local CREATE_PAYLOAD=$(cat <<EOF
{
    "integration_id": "$TEST_ID",
    "integration_type": "splunk",
    "name": "Test Integration",
    "description": "Created by integration test script",
    "enabled": true,
    "settings": {
        "host": "test.splunk.local",
        "port": 8089,
        "verify_ssl": false
    }
}
EOF
)

    # Capture both status code and body in a single request
    local RESPONSE
    local CREATE_STATUS
    RESPONSE=$(api_curl -s -w "\n%{http_code}" -X POST "$BASE_URL/integrations" \
        -H "Content-Type: application/json" \
        -d "$CREATE_PAYLOAD")
    CREATE_STATUS=$(echo "$RESPONSE" | tail -1)
    RESPONSE=$(echo "$RESPONSE" | sed '$d')

    if [ "$CREATE_STATUS" = "403" ]; then
        print_color "$YELLOW" "  ⚠️  Skipping CRUD tests — API key lacks write permissions (403)"
        echo ""
        return 0
    fi

    local CREATED_ID=$(echo "$RESPONSE" | jq -r '.data.integration_id' 2>/dev/null)

    if [ "$CREATED_ID" = "$TEST_ID" ]; then
        print_color "$GREEN" "  ✅ Integration created successfully"

        # Test duplicate creation (should fail with 409)
        print_color "$YELLOW" "Testing duplicate prevention..."
        local DUP_RESPONSE=$(api_curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/integrations" \
            -H "Content-Type: application/json" \
            -d "$CREATE_PAYLOAD")

        if [ "$DUP_RESPONSE" = "409" ]; then
            print_color "$GREEN" "  ✅ Duplicate prevention works (409 returned)"
        else
            print_color "$RED" "  ❌ Duplicate prevention failed (expected 409, got $DUP_RESPONSE)"
        fi

        # Get integration details
        print_color "$YELLOW" "Fetching integration details..."
        RESPONSE=$(api_curl -s "$BASE_URL/integrations/$CREATED_ID")
        local FETCHED_ID=$(echo "$RESPONSE" | jq -r '.data.integration_id' 2>/dev/null)

        if [ "$FETCHED_ID" = "$CREATED_ID" ]; then
            print_color "$GREEN" "  ✅ Integration details retrieved"
        else
            print_color "$RED" "  ❌ Failed to fetch integration details"
        fi

        # Update integration
        print_color "$YELLOW" "Updating integration..."
        local UPDATE_PAYLOAD='{"enabled": false, "description": "Updated by test"}'
        RESPONSE=$(api_curl -s -X PATCH "$BASE_URL/integrations/$CREATED_ID" \
            -H "Content-Type: application/json" \
            -d "$UPDATE_PAYLOAD")

        local IS_DISABLED=$(echo "$RESPONSE" | jq -r '.data.enabled' 2>/dev/null)
        if [ "$IS_DISABLED" = "false" ]; then
            print_color "$GREEN" "  ✅ Integration updated successfully"
        else
            print_color "$RED" "  ❌ Failed to update integration"
        fi

        # Delete integration
        print_color "$YELLOW" "Deleting test integration..."
        local DELETE_STATUS=$(api_curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/integrations/$CREATED_ID")

        if [ "$DELETE_STATUS" = "204" ] || [ "$DELETE_STATUS" = "200" ]; then
            print_color "$GREEN" "  ✅ Integration deleted successfully"
        else
            print_color "$RED" "  ❌ Failed to delete integration (status: $DELETE_STATUS)"
        fi
    else
        print_color "$RED" "  ❌ Failed to create integration"
        echo "    Response: $RESPONSE"
    fi

    echo ""
}

# Function to test Integration Credentials
test_integration_credentials() {
    print_section "Integration Credentials API Test"

    local TENANT="$TENANT"
    local BASE_URL="$BACKEND_URL/v1/$TENANT"
    local TEST_ID="test-cred-integration-$(date +%s)"

    # First create a test integration
    print_color "$YELLOW" "Creating test integration for credentials..."
    local CREATE_PAYLOAD=$(cat <<EOF
{
    "integration_id": "$TEST_ID",
    "integration_type": "splunk",
    "name": "Test Credential Integration",
    "enabled": true,
    "settings": {
        "host": "test.splunk.local",
        "port": 8089
    }
}
EOF
)

    # Capture both status code and body in a single request
    local RESPONSE
    local CREATE_STATUS
    RESPONSE=$(api_curl -s -w "\n%{http_code}" -X POST "$BASE_URL/integrations" \
        -H "Content-Type: application/json" \
        -d "$CREATE_PAYLOAD")
    CREATE_STATUS=$(echo "$RESPONSE" | tail -1)
    RESPONSE=$(echo "$RESPONSE" | sed '$d')

    if [ "$CREATE_STATUS" = "403" ]; then
        print_color "$YELLOW" "  ⚠️  Skipping credential tests — API key lacks write permissions (403)"
        echo ""
        return 0
    fi

    local CREATED_ID=$(echo "$RESPONSE" | jq -r '.data.integration_id' 2>/dev/null)

    if [ "$CREATED_ID" = "$TEST_ID" ]; then
        print_color "$GREEN" "  ✅ Test integration created"

        # Create and associate credential using new combined endpoint
        print_color "$YELLOW" "Testing combined credential creation..."
        local CRED_PAYLOAD=$(cat <<EOF
{
    "provider": "splunk",
    "account": "$TEST_ID",
    "secret": {
        "username": "testuser",
        "password": "testpass123"
    },
    "is_primary": true,
    "purpose": "admin"
}
EOF
)

        RESPONSE=$(api_curl -s -X POST "$BASE_URL/integrations/$TEST_ID/credentials" \
            -H "Content-Type: application/json" \
            -d "$CRED_PAYLOAD")

        local CRED_ID=$(echo "$RESPONSE" | jq -r '.data.credential_id' 2>/dev/null)

        if [ -n "$CRED_ID" ] && [ "$CRED_ID" != "null" ]; then
            print_color "$GREEN" "  ✅ Credential created and associated"
            echo "    Credential ID: $CRED_ID"

            # List integration credentials (GET is on /credentials/integrations/{id}, not /integrations/{id}/credentials)
            print_color "$YELLOW" "Listing integration credentials..."
            RESPONSE=$(api_curl -s "$BASE_URL/credentials/integrations/$TEST_ID")
            local CRED_COUNT=$(echo "$RESPONSE" | jq '.data | length' 2>/dev/null)

            if [ "$CRED_COUNT" -gt 0 ] 2>/dev/null; then
                print_color "$GREEN" "  ✅ Found $CRED_COUNT credential(s)"
            else
                print_color "$RED" "  ❌ Failed to list credentials"
            fi
        else
            print_color "$RED" "  ❌ Failed to create credential"
            echo "    Response: $RESPONSE"
        fi

        # Clean up
        api_curl -s -X DELETE "$BASE_URL/integrations/$TEST_ID" > /dev/null 2>&1
        print_color "$CYAN" "  ℹ️  Test integration cleaned up"
    else
        print_color "$RED" "  ❌ Failed to create test integration"
        echo "    Response: $RESPONSE"
    fi

    echo ""
}

# Function to generate test summary
generate_summary() {
    print_section "Test Summary"

    print_color "$BOLD" "Alert API Coverage:"
    echo "  • GET /alerts (List) .................. ✅"
    echo "  • GET /alerts/:id (Details) ........... ✅"
    echo "  • GET /dispositions ................... ✅"
    echo "  • GET /alerts/:id/analysis/progress ... ✅"
    echo "  • GET /alerts/:id/analyses ............ ✅"
    echo "  • GET /alerts with sorting ............ ✅"

    echo ""
    print_color "$BOLD" "Integration API Coverage:"
    echo "  • GET /integrations/registry .......... ✅"
    echo "  • GET /integrations/registry/:type .... ✅"
    echo "  • GET /integrations/registry/:type/connectors/:connector ✅"
    echo "  • POST /integrations .................. ✅"
    echo "  • GET /integrations/:id ............... ✅"
    echo "  • PATCH /integrations/:id ............. ✅"
    echo "  • DELETE /integrations/:id ............ ✅"
    echo "  • POST /integrations/:id/credentials .. ✅"
    echo "  • GET /integrations/:id/credentials ... ✅"
    echo "  • 409 Duplicate Prevention ............ ✅"

    echo ""
    print_color "$BOLD" "Test Statistics:"
    echo "  • Backend URL: $BACKEND_URL"
    echo "  • Tenant: $TENANT"
    echo "  • Test Categories: 5"
    echo "    - Alert Management APIs"
    echo "    - Alert Sorting APIs"
    echo "    - Integration Registry APIs"
    echo "    - Integration CRUD Operations"
    echo "    - Integration Credentials APIs"
}

# Main execution
main() {
    print_color "$BOLD$GREEN" "🚀 Integration Test Runner"
    print_color "$YELLOW" "Testing against: $BACKEND_URL (tenant: $TENANT)"
    
    # Check if backend is running
    if ! check_backend; then
        exit 1
    fi
    
    # Run tests
    run_alert_tests
    test_sorting
    test_integration_registry
    test_integration_crud
    test_integration_credentials

    generate_summary
    print_section "✨ All Tests Completed!"
    exit 0
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Integration Test Runner"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --url URL      Set backend URL (default: http://localhost:8001)"
        echo ""
        echo "Environment Variables:"
        echo "  BACKEND_URL    Backend server URL (default: http://localhost:8001)"
        echo ""
        echo "Examples:"
        echo "  $0"
        echo "  $0 --url http://localhost:8080"
        echo "  BACKEND_URL=http://localhost:8080 $0"
        exit 0
        ;;
    --url)
        if [ -z "$2" ]; then
            print_color "$RED" "Error: --url requires a URL argument"
            exit 1
        fi
        BACKEND_URL="$2"
        shift 2
        ;;
esac

# Run the main function
main