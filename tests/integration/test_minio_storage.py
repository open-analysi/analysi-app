"""Integration tests for MinIO storage functionality."""

import pytest

from analysi.services.storage import StorageManager

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_minio_storage_large_content(minio_test_bucket):
    """Test that large content (>512KB) triggers MinIO storage and is actually stored."""
    storage_manager = StorageManager()

    # Create content larger than 512KB threshold
    large_content = "x" * (600 * 1024)  # 600KB of data
    content_type = "text/plain"
    tenant_id = "test-tenant"
    task_run_id = "test-task-run-123"
    storage_purpose = "input"

    # Verify content size exceeds threshold
    content_size = len(large_content.encode("utf-8"))
    assert content_size > storage_manager.size_threshold, (
        f"Content size {content_size} should exceed {storage_manager.size_threshold}"
    )

    # Verify storage type selection
    storage_type = storage_manager.select_storage_type(large_content)
    assert storage_type == "s3", (
        f"Large content should select 's3' storage, got '{storage_type}'"
    )

    # Store the content
    storage_info = await storage_manager.store(
        content=large_content,
        content_type=content_type,
        tenant_id=tenant_id,
        task_run_id=task_run_id,
        storage_purpose=storage_purpose,
    )

    # Bucket is managed by minio_test_bucket fixture

    # Verify storage info
    assert storage_info["storage_type"] == "s3"
    assert storage_info["content_type"] == content_type
    assert storage_info["bucket"] == minio_test_bucket
    assert tenant_id in storage_info["location"]
    assert task_run_id in storage_info["location"]
    assert storage_purpose in storage_info["location"]

    # Retrieve the content and verify it matches
    retrieved_content = await storage_manager.retrieve(
        storage_type=storage_info["storage_type"],
        location=storage_info["location"],
        content_type=content_type,
    )

    assert retrieved_content == large_content, "Retrieved content should match original"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_minio_storage_path_generation(minio_test_bucket):
    """Test that MinIO storage paths follow the correct format."""
    storage_manager = StorageManager()

    large_content = "x" * (600 * 1024)  # 600KB
    tenant_id = "cybersec-demo"
    task_run_id = "tr-abc123def456"
    storage_purpose = "output"

    storage_info = await storage_manager.store(
        content=large_content,
        content_type="application/json",
        tenant_id=tenant_id,
        task_run_id=task_run_id,
        storage_purpose=storage_purpose,
    )

    # Bucket is managed by minio_test_bucket fixture

    # Verify path format: {tenant}/task-runs/{YYYY-MM-DD}/{task_run_id}/{purpose}.{ext}
    location = storage_info["location"]
    path_parts = location.split("/")

    assert path_parts[0] == tenant_id
    assert path_parts[1] == "task-runs"
    assert len(path_parts[2]) == 10  # YYYY-MM-DD format
    assert path_parts[3] == task_run_id
    assert path_parts[4] == "output.json"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inline_vs_minio_threshold(minio_test_bucket):
    """Test the 512KB threshold between inline and MinIO storage."""
    storage_manager = StorageManager()

    # Test content just under threshold (should use inline)
    small_content = "x" * (500 * 1024)  # 500KB
    small_storage_type = storage_manager.select_storage_type(small_content)
    assert small_storage_type == "inline"

    # Store small content
    small_storage_info = await storage_manager.store(
        content=small_content,
        content_type="text/plain",
        tenant_id="test-tenant",
        task_run_id="test-small",
        storage_purpose="input",
    )
    assert small_storage_info["storage_type"] == "inline"
    assert small_storage_info["location"] == small_content  # Stored directly

    # Test content at threshold (should use MinIO)
    threshold_content = "x" * (512 * 1024)  # Exactly 512KB
    threshold_storage_type = storage_manager.select_storage_type(threshold_content)
    assert threshold_storage_type == "s3"

    # Store threshold content
    threshold_storage_info = await storage_manager.store(
        content=threshold_content,
        content_type="text/plain",
        tenant_id="test-tenant",
        task_run_id="test-threshold",
        storage_purpose="input",
    )
    # Bucket is managed by minio_test_bucket fixture
    assert threshold_storage_info["storage_type"] == "s3"
    assert threshold_storage_info["location"] != threshold_content  # Stored in MinIO


@pytest.mark.integration
@pytest.mark.asyncio
async def test_minio_with_different_content_types(minio_test_bucket):
    """Test MinIO storage with various content types."""
    storage_manager = StorageManager()

    # Test with JSON content
    json_content = '{"data": "' + "x" * (600 * 1024) + '"}'
    json_storage_info = await storage_manager.store(
        content=json_content,
        content_type="application/json",
        tenant_id="test-tenant",
        task_run_id="test-json",
        storage_purpose="output",
    )

    # Bucket is managed by minio_test_bucket fixture

    assert json_storage_info["location"].endswith(".json")
    retrieved_json = await storage_manager.retrieve(
        "s3", json_storage_info["location"], "application/json"
    )
    assert retrieved_json == json_content

    # Test with CSV content - make it large enough for MinIO
    csv_content = "col1,col2,col3\n" + ("row,data,here\n" * 50000)  # Large CSV >512KB
    csv_storage_info = await storage_manager.store(
        content=csv_content,
        content_type="text/csv",
        tenant_id="test-tenant",
        task_run_id="test-csv",
        storage_purpose="input",
    )

    # Bucket is managed by minio_test_bucket fixture

    assert csv_storage_info["location"].endswith(".csv")
    retrieved_csv = await storage_manager.retrieve(
        "s3", csv_storage_info["location"], "text/csv"
    )
    assert retrieved_csv == csv_content
