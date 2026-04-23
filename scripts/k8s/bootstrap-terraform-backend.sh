#!/usr/bin/env bash
# One-time bootstrap: create S3 bucket + DynamoDB table for Terraform state.
# Run this once before the first `make eks-up`.
#
# Region is hardcoded to us-east-1 to match backend.tf. If you need a different
# region, update BOTH this script AND deployments/terraform/environments/eks-live/backend.tf.
#
# Usage: bash scripts/k8s/bootstrap-terraform-backend.sh

set -euo pipefail

REGION="us-east-1"
BUCKET="analysi-terraform-state"
TABLE="analysi-terraform-locks"

echo "==> Bootstrapping Terraform backend in ${REGION}"

# S3 bucket
if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
    echo "    Bucket ${BUCKET} already exists"
else
    echo "    Creating S3 bucket: ${BUCKET}"
    if [ "${REGION}" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}"
    else
        aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}" \
            --create-bucket-configuration LocationConstraint="${REGION}"
    fi

    aws s3api put-bucket-versioning --bucket "${BUCKET}" \
        --versioning-configuration Status=Enabled

    aws s3api put-bucket-encryption --bucket "${BUCKET}" \
        --server-side-encryption-configuration \
        '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

    aws s3api put-public-access-block --bucket "${BUCKET}" \
        --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

# DynamoDB table for state locking
if aws dynamodb describe-table --table-name "${TABLE}" --region "${REGION}" >/dev/null 2>&1; then
    echo "    DynamoDB table ${TABLE} already exists"
else
    echo "    Creating DynamoDB table: ${TABLE}"
    aws dynamodb create-table \
        --table-name "${TABLE}" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "${REGION}"

    aws dynamodb wait table-exists --table-name "${TABLE}" --region "${REGION}"
fi

echo "==> Bootstrap complete. You can now run: make eks-up"
