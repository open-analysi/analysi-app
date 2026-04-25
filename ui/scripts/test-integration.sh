#!/bin/bash

# Simple wrapper script that calls run_integration_tests.sh
# This script exists to match the npm script reference in package.json

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Forward all arguments to the main integration test script
exec "$SCRIPT_DIR/run_integration_tests.sh" "$@"