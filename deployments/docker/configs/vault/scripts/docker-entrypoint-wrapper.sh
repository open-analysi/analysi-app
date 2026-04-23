#!/bin/sh
# Custom entrypoint wrapper for Vault that runs initialization after startup
set -e

echo "Starting Vault server in dev mode..."

# Start vault server in dev mode in the background
vault server -dev -dev-root-token-id="${VAULT_DEV_ROOT_TOKEN_ID:-dev-root-token}" -dev-listen-address="0.0.0.0:8200" &
VAULT_PID=$!

# Export environment variables for vault CLI
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN_ID:-dev-root-token}"

# Wait for Vault to be ready
echo "Waiting for Vault to be ready..."
while ! vault status > /dev/null 2>&1; do
    sleep 1
done

echo "Vault is ready. Running initialization script..."

# Run the initialization script
/vault/scripts/init-vault.sh

echo "Initialization complete. Vault is running with PID $VAULT_PID"

# Keep the container running by waiting on the vault process
wait $VAULT_PID
