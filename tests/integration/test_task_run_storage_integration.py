"""
Integration tests for task run storage with MinIO and PostgreSQL.

Tests the storage manager functionality for task runs, verifying:
1. Large content storage in MinIO with PostgreSQL references
2. Small content inline storage in PostgreSQL
3. Content retrieval from both storage types
"""

import json
import uuid
from datetime import UTC, datetime

import aioboto3
import pytest

from analysi.models.task_run import TaskRun
from analysi.services.storage import StorageManager

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.fixture
async def cleanup_test_data():
    """Cleanup task runs and MinIO objects created during tests."""
    created_task_run_ids = []  # Store UUIDs not objects
    created_minio_objects = []

    yield created_task_run_ids, created_minio_objects

    # Only cleanup MinIO objects - database cleanup handled by conftest.py
    if created_minio_objects:
        from analysi.config.object_storage import ObjectStorageConfig

        minio_config = ObjectStorageConfig.get_settings(test_mode=True)
        endpoint = minio_config["endpoint"]
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=minio_config["access_key"],
            aws_secret_access_key=minio_config["secret_key"],
        ) as s3_client:
            for obj_key in created_minio_objects:
                try:
                    await s3_client.delete_object(Bucket="analysi-storage", Key=obj_key)
                    print(f"Cleaned up MinIO object: {obj_key}")
                except Exception as e:
                    print(f"Failed to cleanup {obj_key}: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_large_input_stored_in_minio_with_db_reference(
    cleanup_test_data, integration_test_session
):
    """
    Test that large input (>512KB) is stored in MinIO and PostgreSQL has the reference.

    This directly tests the storage manager functionality.
    """
    created_task_run_ids, created_minio_objects = cleanup_test_data
    db = integration_test_session

    storage_manager = StorageManager()

    # Create large input content (>512KB)
    large_input = json.dumps(
        {"data": "x" * (600 * 1024), "task": "test-task"}  # 600KB of JSON data
    )

    # Store using storage manager
    task_run_id = str(uuid.uuid4())
    storage_info = await storage_manager.store(
        content=large_input,
        content_type="application/json",
        tenant_id="test-tenant",
        task_run_id=task_run_id,
        storage_purpose="input",
    )

    # Verify storage went to MinIO
    assert storage_info["storage_type"] == "s3"
    assert "test-tenant/task-runs/" in storage_info["location"]
    assert storage_info["location"].endswith(".json")

    # Track for cleanup
    created_minio_objects.append(storage_info["location"])

    # Create task run in database with storage reference
    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=None,  # Ad-hoc execution
        cy_script="TEST_SCRIPT",
        status="running",
        input_type=storage_info["storage_type"],
        input_location=storage_info["location"],
        input_content_type=storage_info["content_type"],
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task_run)
    await db.commit()
    await db.refresh(task_run)
    created_task_run_ids.append(task_run.id)

    # Verify database has correct storage metadata
    assert task_run.input_type == "s3"
    assert task_run.input_location == storage_info["location"]
    assert task_run.input_content_type == "application/json"

    # Retrieve content using storage manager
    retrieved_content = await storage_manager.retrieve(
        storage_type=task_run.input_type,
        location=task_run.input_location,
        content_type=task_run.input_content_type,
    )

    assert retrieved_content == large_input
    print(f"✓ Large input stored in MinIO at: {task_run.input_location}")
    print(f"✓ Retrieved {len(retrieved_content)} bytes successfully")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_small_input_stored_inline_in_database(
    cleanup_test_data, integration_test_session
):
    """
    Test that small input (<512KB) is stored inline in PostgreSQL.

    This directly tests the storage manager functionality.
    """
    created_task_run_ids, _ = cleanup_test_data
    db = integration_test_session

    storage_manager = StorageManager()

    # Create small input content (<512KB)
    small_input = json.dumps({"data": "small test data", "task": "test-task"})

    # Store using storage manager
    task_run_id = str(uuid.uuid4())
    storage_info = await storage_manager.store(
        content=small_input,
        content_type="application/json",
        tenant_id="test-tenant",
        task_run_id=task_run_id,
        storage_purpose="input",
    )

    # Verify inline storage
    assert storage_info["storage_type"] == "inline"
    assert storage_info["location"] == small_input  # Content stored directly

    # Create task run in database with inline storage
    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=None,  # Ad-hoc execution
        cy_script="TEST_SCRIPT",
        status="running",
        input_type=storage_info["storage_type"],
        input_location=storage_info["location"],
        input_content_type=storage_info["content_type"],
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task_run)
    await db.commit()
    await db.refresh(task_run)
    created_task_run_ids.append(task_run.id)

    # Verify database has inline storage
    assert task_run.input_type == "inline"
    assert task_run.input_location == small_input

    # Retrieve content using storage manager
    retrieved_content = await storage_manager.retrieve(
        storage_type=task_run.input_type,
        location=task_run.input_location,
        content_type=task_run.input_content_type,
    )

    assert retrieved_content == small_input
    print("✓ Small input stored inline in database")
    print(f"✓ Retrieved {len(retrieved_content)} bytes successfully")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_execution_output_storage(
    cleanup_test_data, integration_test_session
):
    """
    Test task execution output storage based on content size.
    """
    created_task_run_ids, created_minio_objects = cleanup_test_data
    db = integration_test_session

    storage_manager = StorageManager()

    # Create a task run first
    task_run_id = str(uuid.uuid4())
    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=None,  # Ad-hoc execution
        cy_script="GENERATE_OUTPUT",
        status="running",
        input_type="inline",
        input_location='{"test": "input"}',
        input_content_type="application/json",
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task_run)
    await db.commit()
    created_task_run_ids.append(task_run.id)

    # Simulate task execution generating large output
    large_output = json.dumps(
        {
            "results": ["result_" + str(i) for i in range(50000)],  # Large output
            "summary": "Processing completed",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # Store output
    output_storage = await storage_manager.store(
        content=large_output,
        content_type="application/json",
        tenant_id=task_run.tenant_id,
        task_run_id=task_run.id,
        storage_purpose="output",
    )

    # Verify MinIO storage for large output
    assert output_storage["storage_type"] == "s3"
    created_minio_objects.append(output_storage["location"])

    # Update task run with output reference
    task_run.output_type = output_storage["storage_type"]
    task_run.output_location = output_storage["location"]
    task_run.output_content_type = output_storage["content_type"]
    task_run.status = "completed"
    task_run.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task_run)

    # Verify output storage in DB
    assert task_run.output_type == "s3"
    assert "test-tenant/task-runs/" in task_run.output_location
    assert task_run.output_location.endswith(".json")

    # Retrieve output
    retrieved_output = await storage_manager.retrieve(
        storage_type=task_run.output_type,
        location=task_run.output_location,
        content_type=task_run.output_content_type,
    )

    assert retrieved_output == large_output
    parsed_output = json.loads(retrieved_output)
    assert len(parsed_output["results"]) == 50000
    assert parsed_output["summary"] == "Processing completed"

    print(f"✓ Large output stored in MinIO at: {task_run.output_location}")
    print(f"✓ Retrieved {len(retrieved_output)} bytes of output successfully")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_storage_threshold_boundary(cleanup_test_data):
    """
    Test storage selection at exactly 512KB boundary.
    """
    created_task_run_ids, created_minio_objects = cleanup_test_data

    storage_manager = StorageManager()

    # Content exactly at 512KB
    content_512kb = "x" * (512 * 1024)

    # Content just under 512KB
    content_under = "x" * (512 * 1024 - 1)

    # Generate UUIDs
    task_run_id_1 = str(uuid.uuid4())
    task_run_id_2 = str(uuid.uuid4())

    # Test at threshold
    at_threshold = await storage_manager.store(
        content=content_512kb,
        content_type="text/plain",
        tenant_id="test-tenant",
        task_run_id=task_run_id_1,
        storage_purpose="input",
    )

    # Should use MinIO at exactly 512KB
    assert at_threshold["storage_type"] == "s3"
    created_minio_objects.append(at_threshold["location"])

    # Test just under threshold
    under_threshold = await storage_manager.store(
        content=content_under,
        content_type="text/plain",
        tenant_id="test-tenant",
        task_run_id=task_run_id_2,
        storage_purpose="input",
    )

    # Should use inline just under 512KB
    assert under_threshold["storage_type"] == "inline"
    assert under_threshold["location"] == content_under

    print("✓ At 512KB: uses MinIO (s3)")
    print("✓ Under 512KB: uses inline storage")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_stores_correct_references(integration_test_session):
    """
    Directly verify that PostgreSQL stores the correct storage references.
    """
    db = integration_test_session
    storage_manager = StorageManager()

    # Create with large input
    large_content = "x" * (600 * 1024)
    task_run_id = str(uuid.uuid4())
    storage_info = await storage_manager.store(
        content=large_content,
        content_type="text/plain",
        tenant_id="test-tenant",
        task_run_id=task_run_id,
        storage_purpose="input",
    )

    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=None,  # Ad-hoc execution
        cy_script="TEST",
        status="running",
        input_type=storage_info["storage_type"],
        input_location=storage_info["location"],
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task_run)
    await db.commit()
    await db.refresh(task_run)

    # Verify storage reference is correct
    assert task_run.input_type == "s3"
    assert task_run.input_location == storage_info["location"]
    assert "test-tenant/task-runs/" in task_run.input_location

    print(f"✓ Database correctly stores MinIO reference: {task_run.input_location}")
