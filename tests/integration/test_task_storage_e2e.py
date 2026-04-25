"""
End-to-end integration tests for task execution with storage.

Tests the complete flow:
1. Execute task with large input/output
2. Verify PostgreSQL stores references to MinIO
3. Verify we can retrieve the task run with correct storage metadata
"""

import json
import uuid
from datetime import UTC, datetime

import pytest

from analysi.db.session import get_db
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component, ComponentKind
from analysi.models.task import Task, TaskFunction
from analysi.models.task_run import TaskRun
from analysi.services.storage import StorageManager

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


async def create_test_task(session, tenant_id: str, name: str = "Test Task") -> Task:
    """Helper to create a task for testing."""
    # Create component first
    component = Component(
        tenant_id=tenant_id,
        kind=ComponentKind.TASK,
        name=name,
        description=f"{name} for integration testing",
        created_by=str(SYSTEM_USER_ID),
    )
    session.add(component)
    await session.flush()

    # Create task with the component
    task = Task(
        component_id=component.id,
        directive=f"Execute {name}",
        function=TaskFunction.REASONING,
        script="TEST_SCRIPT",  # Field is 'script' not 'cy_script'
    )
    session.add(task)
    await session.flush()

    return task


@pytest.mark.integration
@pytest.mark.asyncio
async def test_large_input_storage_e2e(minio_test_bucket, integration_test_session):
    """
    Test end-to-end flow: large input -> MinIO storage -> DB reference -> retrieval.
    """

    # Initialize services
    storage_manager = StorageManager()
    # task_run_service = TaskRunService()  # Unused

    # Create large input (>512KB)
    large_input = json.dumps(
        {"data": "x" * (600 * 1024), "metadata": {"test": "large_input"}}  # 600KB
    )

    # Use integration_test_session directly
    db = integration_test_session
    # Create a test task
    task = await create_test_task(db, "test-tenant", "Large Input Test Task")
    await db.commit()

    # Generate task run ID
    task_run_id = str(uuid.uuid4())
    # Step 1: Store large input using storage manager
    input_storage = await storage_manager.store(
        content=large_input,
        content_type="application/json",
        tenant_id="test-tenant",
        task_run_id=task_run_id,
        storage_purpose="input",
    )

    # Verify storage went to MinIO
    assert input_storage["storage_type"] == "s3", "Large content should use MinIO"
    assert "test-tenant/task-runs/" in input_storage["location"]
    assert input_storage["location"].endswith(".json")

    # MinIO cleanup handled by minio_test_bucket fixture

    # Step 2: Create task run with storage reference in DB
    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=task.component_id,  # Use the actual task ID
        cy_script="PROCESS_LARGE_DATA",
        status="running",
        input_type=input_storage["storage_type"],
        input_location=input_storage["location"],
        input_content_type=input_storage["content_type"],
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task_run)
    await db.commit()
    await db.refresh(task_run)

    # Step 3: Verify DB has correct storage metadata
    assert task_run.input_type == "s3"
    assert task_run.input_location == input_storage["location"]
    assert task_run.input_content_type == "application/json"

    # Step 4: Retrieve input using storage manager (simulating API retrieval)
    retrieved_content = await storage_manager.retrieve(
        storage_type=task_run.input_type,
        location=task_run.input_location,
        content_type=task_run.input_content_type,
    )

    # Verify retrieved content matches original
    assert retrieved_content == large_input
    assert json.loads(retrieved_content)["metadata"]["test"] == "large_input"

    print(f"✓ Large input stored in MinIO at: {task_run.input_location}")
    print(f"✓ Retrieved {len(retrieved_content)} bytes successfully")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_small_input_inline_storage_e2e(integration_test_session):
    """
    Test that small input (<512KB) is stored inline in PostgreSQL.
    """

    storage_manager = StorageManager()

    # Create small input
    small_input = json.dumps({"data": "small test data", "config": {"mode": "test"}})

    # Use integration_test_session directly
    db = integration_test_session
    # Create a test task with unique name
    task = await create_test_task(
        db, "test-tenant", f"Small Input Test Task {uuid.uuid4().hex[:8]}"
    )
    await db.commit()

    # Generate task run ID
    task_run_id = str(uuid.uuid4())
    # Store small input
    input_storage = await storage_manager.store(
        content=small_input,
        content_type="application/json",
        tenant_id="test-tenant",
        task_run_id=task_run_id,
        storage_purpose="input",
    )

    # Verify inline storage
    assert input_storage["storage_type"] == "inline"
    assert input_storage["location"] == small_input  # Content stored directly

    # Create task run with inline storage
    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=task.component_id,
        cy_script="SIMPLE_TASK",
        status="running",
        input_type=input_storage["storage_type"],
        input_location=input_storage["location"],
        input_content_type=input_storage["content_type"],
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db.add(task_run)
    await db.commit()
    await db.refresh(task_run)

    # Verify inline storage in DB
    assert task_run.input_type == "inline"
    assert task_run.input_location == small_input

    # Retrieve using storage manager
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
async def test_task_output_storage_e2e(minio_test_bucket, integration_test_session):
    """
    Test task execution output storage based on size.
    """

    storage_manager = StorageManager()

    # Use integration_test_session directly
    db = integration_test_session
    # Create a test task
    task = await create_test_task(db, "test-tenant", "Output Storage Test Task")
    await db.commit()

    # Generate task run ID
    task_run_id = str(uuid.uuid4())
    # Create task run first
    task_run = TaskRun(
        id=task_run_id,
        tenant_id="test-tenant",
        task_id=task.component_id,
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
    # MinIO cleanup handled by minio_test_bucket fixture

    # Update task run with output reference
    task_run.output_type = output_storage["storage_type"]
    task_run.output_location = output_storage["location"]
    task_run.output_content_type = output_storage["content_type"]
    task_run.status = (
        "completed"  # Valid status values: running, succeeded, failed, paused_by_user
    )
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
async def test_storage_threshold_at_boundary(minio_test_bucket):
    """
    Test storage selection at exactly 512KB boundary.
    """

    storage_manager = StorageManager()

    # Content exactly at 512KB
    content_512kb = "x" * (512 * 1024)

    # Content just under 512KB
    content_under = "x" * (512 * 1024 - 1)

    # Generate UUIDs
    task_run_id_1 = str(uuid.uuid4())
    task_run_id_2 = str(uuid.uuid4())

    async for _db in get_db():
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
        # MinIO cleanup handled by minio_test_bucket fixture

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
async def test_storage_retrieval_consistency(minio_test_bucket):
    """
    Test that content remains consistent through store/retrieve cycle.
    """

    storage_manager = StorageManager()

    # Test with various content types
    test_cases = [
        {
            "content": json.dumps({"data": "x" * 600 * 1024}),  # Large JSON
            "content_type": "application/json",
            "expected_storage": "s3",
        },
        {
            "content": "Small text content",  # Small text
            "content_type": "text/plain",
            "expected_storage": "inline",
        },
        {
            "content": "col1,col2,col3\n" + "row1,row2,row3\n" * 40000,  # Large CSV
            "content_type": "text/csv",
            "expected_storage": "s3",
        },
    ]

    for _i, test_case in enumerate(test_cases):
        task_run_id = str(uuid.uuid4())
        storage_info = await storage_manager.store(
            content=test_case["content"],
            content_type=test_case["content_type"],
            tenant_id="test-tenant",
            task_run_id=task_run_id,
            storage_purpose="input",
        )

        # MinIO cleanup handled by minio_test_bucket fixture

        # Verify expected storage type
        assert storage_info["storage_type"] == test_case["expected_storage"]

        # Retrieve and verify consistency
        retrieved = await storage_manager.retrieve(
            storage_type=storage_info["storage_type"],
            location=storage_info["location"],
            content_type=test_case["content_type"],
        )

        assert retrieved == test_case["content"]
        print(
            f"✓ {test_case['content_type']}: consistent through {storage_info['storage_type']} storage"
        )
