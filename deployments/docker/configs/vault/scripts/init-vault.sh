#!/bin/sh
# Vault initialization script for dev mode
# This script sets up Transit engine and creates encryption keys

set -e

# In dev mode, we need to check if transit engines exist, not just a marker file
# since dev mode doesn't persist data across restarts

echo "Waiting for Vault to be ready..."
until vault status > /dev/null 2>&1; do
    sleep 1
done

echo "Vault is ready. Checking transit engines..."

# Check if initialization is needed by looking for transit engines
if vault secrets list | grep -q "^transit-dev/"; then
    echo "Transit engines already configured, skipping initialization."
    exit 0
fi

echo "Transit engines not found, initializing..."

# Enable Transit secrets engines for different environments
for env in "dev" "test"; do
    echo "Enabling transit-${env} engine..."
    vault secrets enable -path=transit-${env} transit
done

echo "Transit engines enabled."

# Create encryption keys for known tenants in each environment
for env in "dev" "test"; do
    echo "Setting up keys for ${env} environment..."
    for tenant in "default" "test-tenant" "tenant-a" "tenant-b"; do
        key_name="${env}-tenant-${tenant}"

        # Check if key exists
        if vault read -field=latest_version "transit-${env}/keys/${key_name}" > /dev/null 2>&1; then
            echo "Key ${key_name} already exists in transit-${env}"
        else
            echo "Creating encryption key ${key_name} in transit-${env}..."
            vault write -f "transit-${env}/keys/${key_name}" \
                type="aes256-gcm96" \
                derived=false \
                exportable=false \
                allow_plaintext_backup=false
            echo "Key ${key_name} created."
        fi
    done
done

# Enable key rotation for all keys (optional)
# for tenant in "default" "test-tenant" "tenant-a" "tenant-b"; do
#     key_name="tenant-${tenant}"
#     vault write -f "transit/keys/${key_name}/rotate"
# done

echo "Vault initialization complete."
