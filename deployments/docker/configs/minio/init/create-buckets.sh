#!/bin/bash
#
# MinIO Bucket Initialization Script
# Creates required buckets for analysi service
#

set -e

echo "🪣 MinIO Bucket Initialization Started"

# Wait for MinIO to be ready
echo "⏳ Waiting for MinIO server to be ready..."
until mc --help >/dev/null 2>&1; do
    echo "⏳ mc command not ready, waiting 1 second..."
    sleep 1
done

# Get configuration from environment variables (with fallbacks)
MINIO_HOST="${MINIO_HOST:-minio}"
MINIO_PORT="${MINIO_PORT:-9000}"
MINIO_URL="http://${MINIO_HOST}:${MINIO_PORT}"
ACCESS_KEY="${MINIO_ROOT_USER:-minioadmin}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:-minioadmin}"
BUCKET_NAME="${MINIO_BUCKET:-analysi-storage}"
ARTIFACTS_BUCKET="${ARTIFACTS_BUCKET:-analysi-storage}"
TEST_BUCKET="${TEST_BUCKET:-analysi-storage-test}"

echo "🔧 Configuration:"
echo "   MinIO URL: $MINIO_URL"
echo "   Access Key: $ACCESS_KEY"
echo "   General Bucket: $BUCKET_NAME"
echo "   Artifacts Bucket: $ARTIFACTS_BUCKET"
echo "   Test Bucket: $TEST_BUCKET"

# Configure MinIO client (try multiple times as MinIO might still be starting)
echo "🔧 Configuring MinIO client..."
RETRIES=0
until mc alias set minio $MINIO_URL $ACCESS_KEY $SECRET_KEY 2>/dev/null; do
    RETRIES=$((RETRIES + 1))
    if [ $RETRIES -gt 30 ]; then
        echo "❌ Failed to connect to MinIO after 30 attempts"
        echo "   URL: $MINIO_URL"
        echo "   Credentials: $ACCESS_KEY / $SECRET_KEY"
        exit 1
    fi
    echo "⏳ MinIO not ready yet, attempt $RETRIES/30, waiting 2 seconds..."
    sleep 2
done
echo "✅ MinIO client configured successfully"

# Create general purpose bucket
echo "🪣 Creating bucket: $BUCKET_NAME"
if mc ls minio/$BUCKET_NAME 2>/dev/null; then
    echo "✅ Bucket $BUCKET_NAME already exists"
else
    mc mb minio/$BUCKET_NAME
    echo "✅ Bucket $BUCKET_NAME created successfully"
fi

# Create artifacts bucket (if different from general bucket)
if [ "$ARTIFACTS_BUCKET" != "$BUCKET_NAME" ]; then
    echo "🪣 Creating artifacts bucket: $ARTIFACTS_BUCKET"
    if mc ls minio/$ARTIFACTS_BUCKET 2>/dev/null; then
        echo "✅ Bucket $ARTIFACTS_BUCKET already exists"
    else
        mc mb minio/$ARTIFACTS_BUCKET
        echo "✅ Bucket $ARTIFACTS_BUCKET created successfully"
    fi
fi

# Create test bucket (used by integration tests)
if [ "$TEST_BUCKET" != "$BUCKET_NAME" ]; then
    echo "🪣 Creating test bucket: $TEST_BUCKET"
    if mc ls minio/$TEST_BUCKET 2>/dev/null; then
        echo "✅ Bucket $TEST_BUCKET already exists"
    else
        mc mb minio/$TEST_BUCKET
        echo "✅ Bucket $TEST_BUCKET created successfully"
    fi
fi

# Set public read policy for development (optional - can be removed for production)
echo "🔒 Setting bucket policies for development..."
mc anonymous set download minio/$BUCKET_NAME 2>/dev/null || echo "⚠️  Could not set anonymous policy for $BUCKET_NAME (this is ok for production)"
if [ "$ARTIFACTS_BUCKET" != "$BUCKET_NAME" ]; then
    mc anonymous set download minio/$ARTIFACTS_BUCKET 2>/dev/null || echo "⚠️  Could not set anonymous policy for $ARTIFACTS_BUCKET (this is ok for production)"
fi
if [ "$TEST_BUCKET" != "$BUCKET_NAME" ]; then
    mc anonymous set download minio/$TEST_BUCKET 2>/dev/null || echo "⚠️  Could not set anonymous policy for $TEST_BUCKET (this is ok for production)"
fi

# Create test directory structure to validate setup
echo "📁 Creating test directory structure..."
echo "test-content" | mc pipe minio/$BUCKET_NAME/test-tenant/task-runs/$(date +%Y-%m-%d)/test-structure.txt
echo "✅ Test structure created successfully"

# List bucket contents to verify
echo "📋 Bucket contents:"
mc ls minio/$BUCKET_NAME --recursive

echo "🎉 MinIO initialization completed successfully!"
echo "📍 General Bucket: $BUCKET_NAME"
if [ "$ARTIFACTS_BUCKET" != "$BUCKET_NAME" ]; then
    echo "📍 Artifacts Bucket: $ARTIFACTS_BUCKET"
fi
echo "🌐 MinIO Console: http://localhost:${MINIO_CONSOLE_EXTERNAL_PORT:-9001}"
echo "🔐 Credentials: $ACCESS_KEY / $SECRET_KEY"
