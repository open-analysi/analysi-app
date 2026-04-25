"""
Integration tests for auto-artifact capture during Cy script execution.

Tests that integration tool calls automatically create artifacts with
artifact_type='tool_execution' and source='auto_capture'.

Key insight: TaskExecutionService.execute_single_task() takes task_run_id
and tenant_id and creates its own isolated session.
Artifacts are committed inside the execution and visible via the test session.
"""

import json
import zlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component
from analysi.models.integration import Integration
from analysi.models.task import Task
from analysi.models.task_run import TaskRun
from analysi.repositories.artifact_repository import ArtifactRepository
from analysi.services.task_execution import TaskExecutionService


@pytest.mark.asyncio
@pytest.mark.integration
class TestAutoArtifactCapture:
    """Test automatic artifact capture for integration tool calls."""

    @pytest.fixture
    async def setup_echo_edr_integration(self, integration_test_session: AsyncSession):
        """Create echo_edr integration and a reusable Task for tests."""
        tenant_id = f"artifact-test-{uuid4().hex[:8]}"
        integration_id = f"test-echo-{uuid4().hex[:8]}"
        component_id = uuid4()
        task_id = uuid4()

        # Create an echo_edr integration for this tenant
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo EDR for Artifact Capture",
            enabled=True,
            settings={"api_url": "http://test-server:8000"},
        )
        integration_test_session.add(integration)

        # Create a Component for the Task (required for foreign key constraint)
        component = Component(
            id=component_id,
            tenant_id=tenant_id,
            name="Test Task Component",
            description="Component for auto-artifact capture test task",
            categories=["test"],
            status="enabled",
            kind="task",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create a Task record (required for foreign key constraint)
        task = Task(
            id=task_id,
            component_id=component_id,
            function="processing",
            scope="processing",
            script="return {}",  # Placeholder script
        )
        integration_test_session.add(task)
        # CRITICAL: Commit test data so it's visible to execution
        # (See DECISIONS.md Decision 2: Workflow Testing Pattern)
        await integration_test_session.commit()

        return {
            "tenant_id": tenant_id,
            "integration_id": integration_id,
            # NOTE: TaskRun.task_id FK references task(component_id), not task(id)
            "task_id": component_id,
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_tool_execution_creates_artifact(
        self, integration_test_session: AsyncSession, setup_echo_edr_integration
    ):
        """
        Test that executing an integration tool via Cy script automatically
        creates an artifact with artifact_type='tool_execution'.

        Uses echo_edr::isolate_host which is a mock tool that succeeds
        without requiring a real server.
        """
        tenant_id = setup_echo_edr_integration["tenant_id"]
        integration_id = setup_echo_edr_integration["integration_id"]
        task_id = setup_echo_edr_integration["task_id"]

        # Create a Cy script that calls an integration tool
        # isolate_host is a mock tool that succeeds without a real server
        cy_script = """# Test script for auto-artifact capture
hostname = input["hostname"]
result = app::echo_edr::isolate_host(hostname=hostname)
return {"success": True, "result": result}
"""
        task_run_id = uuid4()

        # Create TaskRun record
        task_run = TaskRun(
            id=task_run_id,
            task_id=task_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            input_type="inline",
            input_location=json.dumps({"hostname": "test-host-artifact"}),
            execution_context={},
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        # CRITICAL: Commit before execution (see DECISIONS.md Decision 2)
        await integration_test_session.commit()

        # Execute the task (task_run_id + tenant_id)
        execution_service = TaskExecutionService()
        await execution_service.execute_single_task(task_run_id, tenant_id)

        # Commit after execution to persist artifacts
        await integration_test_session.commit()

        # Query for artifacts with artifact_type='tool_execution'
        artifact_repo = ArtifactRepository(integration_test_session)
        artifacts_list, _ = await artifact_repo.list(
            tenant_id,
            filters={
                "artifact_type": "tool_execution",
                "task_run_id": str(task_run_id),
            },
        )

        # Find the artifact for our tool call
        matching_artifacts = [
            a for a in artifacts_list if a.name == "app::echo_edr::isolate_host"
        ]

        assert len(matching_artifacts) > 0, (
            f"Expected at least one artifact for app::echo_edr::isolate_host. "
            f"Found {len(artifacts_list)} total tool_execution artifacts with names: "
            f"{[a.name for a in artifacts_list]}"
        )

        artifact = matching_artifacts[0]

        # Verify artifact fields
        assert artifact.artifact_type == "tool_execution"
        assert artifact.source == "auto_capture"
        assert artifact.mime_type == "application/json"
        assert artifact.integration_id == integration_id
        assert artifact.task_run_id == task_run_id

        # Verify content structure
        content = json.loads(zlib.decompress(artifact.inline_content).decode("utf-8"))
        assert "input" in content, f"Artifact content missing 'input': {content}"
        assert "output" in content, f"Artifact content missing 'output': {content}"
        assert "duration_ms" in content, (
            f"Artifact content missing 'duration_ms': {content}"
        )
        assert "timestamp" in content, (
            f"Artifact content missing 'timestamp': {content}"
        )

        # Verify input contains our parameter
        assert content["input"].get("hostname") == "test-host-artifact"

        # Verify output has expected structure from isolate_host mock
        output = content["output"]
        assert output.get("hostname") == "test-host-artifact"
        assert "message" in output  # Mock returns a message field

    @pytest.mark.asyncio
    async def test_artifact_links_to_task_run(
        self, integration_test_session: AsyncSession, setup_echo_edr_integration
    ):
        """
        Test that auto-captured artifacts are linked to the task_run_id
        of the Cy script execution.
        """
        tenant_id = setup_echo_edr_integration["tenant_id"]
        task_id = setup_echo_edr_integration["task_id"]

        cy_script = """result = app::echo_edr::isolate_host(hostname="task-link-test")
return result
"""
        task_run_id = uuid4()

        # Create TaskRun record
        task_run = TaskRun(
            id=task_run_id,
            task_id=task_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            input_type="inline",
            input_location=json.dumps({}),
            execution_context={},
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Execute the task (task_run_id + tenant_id)
        execution_service = TaskExecutionService()
        await execution_service.execute_single_task(task_run_id, tenant_id)

        # Commit after execution
        await integration_test_session.commit()

        # Query for artifacts linked to this task run
        artifact_repo = ArtifactRepository(integration_test_session)
        artifacts_list, _ = await artifact_repo.list(
            tenant_id,
            filters={
                "task_run_id": str(task_run_id),
                "artifact_type": "tool_execution",
            },
        )

        assert len(artifacts_list) > 0, (
            f"Expected artifact linked to task_run_id={task_run_id}"
        )

        # Verify the artifact is for isolate_host and has correct task_run_id
        artifact = artifacts_list[0]
        assert artifact.name == "app::echo_edr::isolate_host"
        assert artifact.task_run_id == task_run_id

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_create_multiple_artifacts(
        self, integration_test_session: AsyncSession, setup_echo_edr_integration
    ):
        """
        Test that a Cy script with multiple tool calls creates
        multiple artifacts (one per tool call).
        """
        tenant_id = setup_echo_edr_integration["tenant_id"]
        task_id = setup_echo_edr_integration["task_id"]

        # Cy script with multiple tool calls
        cy_script = """# Test multiple tool calls
result1 = app::echo_edr::isolate_host(hostname="host1")
result2 = app::echo_edr::isolate_host(hostname="host2")
return {"results": [result1, result2]}
"""
        task_run_id = uuid4()

        # Create TaskRun record
        task_run = TaskRun(
            id=task_run_id,
            task_id=task_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            input_type="inline",
            input_location=json.dumps({}),
            execution_context={},
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Execute the task (task_run_id + tenant_id)
        execution_service = TaskExecutionService()
        await execution_service.execute_single_task(task_run_id, tenant_id)

        # Commit after execution
        await integration_test_session.commit()

        # Query for artifacts linked to this task run
        artifact_repo = ArtifactRepository(integration_test_session)
        artifacts_list, _ = await artifact_repo.list(
            tenant_id,
            filters={
                "task_run_id": str(task_run_id),
                "artifact_type": "tool_execution",
            },
        )

        # Should have 2 artifacts (one per tool call)
        assert len(artifacts_list) >= 2, (
            f"Expected 2 artifacts for 2 tool calls, got {len(artifacts_list)}"
        )

        # Verify both are for isolate_host with different inputs
        hostnames_captured = set()
        for artifact in artifacts_list:
            if artifact.name == "app::echo_edr::isolate_host":
                content = json.loads(
                    zlib.decompress(artifact.inline_content).decode("utf-8")
                )
                hostname = content.get("input", {}).get("hostname")
                if hostname:
                    hostnames_captured.add(hostname)

        assert "host1" in hostnames_captured, "Missing artifact for host1"
        assert "host2" in hostnames_captured, "Missing artifact for host2"

    @pytest.mark.asyncio
    async def test_artifact_captures_duration(
        self, integration_test_session: AsyncSession, setup_echo_edr_integration
    ):
        """
        Test that auto-captured artifacts include execution duration.
        """
        tenant_id = setup_echo_edr_integration["tenant_id"]
        task_id = setup_echo_edr_integration["task_id"]

        cy_script = """result = app::echo_edr::isolate_host(hostname="duration-test")
return result
"""
        task_run_id = uuid4()

        # Create TaskRun record
        task_run = TaskRun(
            id=task_run_id,
            task_id=task_id,
            tenant_id=tenant_id,
            cy_script=cy_script,
            status="running",
            input_type="inline",
            input_location=json.dumps({}),
            execution_context={},
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Execute the task (task_run_id + tenant_id)
        execution_service = TaskExecutionService()
        await execution_service.execute_single_task(task_run_id, tenant_id)

        # Commit after execution
        await integration_test_session.commit()

        # Query for the artifact
        artifact_repo = ArtifactRepository(integration_test_session)
        artifacts_list, _ = await artifact_repo.list(
            tenant_id,
            filters={
                "task_run_id": str(task_run_id),
                "artifact_type": "tool_execution",
                "name": "app::echo_edr::isolate_host",
            },
        )

        assert len(artifacts_list) > 0, "Expected at least one artifact"
        artifact = artifacts_list[0]

        content = json.loads(zlib.decompress(artifact.inline_content).decode("utf-8"))
        assert "duration_ms" in content
        assert isinstance(content["duration_ms"], int)
        assert content["duration_ms"] >= 0, "Duration should be non-negative"
