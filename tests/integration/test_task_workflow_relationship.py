"""
Integration tests for TaskRun-WorkflowRun relationship.
Verifies the relationship works correctly with nullable workflow_run_id.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.task_run import TaskRun
from analysi.models.workflow import Workflow
from analysi.models.workflow_execution import WorkflowRun


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskWorkflowRelationship:
    """Test the TaskRun-WorkflowRun relationship with nullable workflow_run_id."""

    @pytest.mark.asyncio
    async def test_task_run_with_workflow(self, integration_test_session: AsyncSession):
        """Test TaskRun with a workflow relationship."""
        # First create a Workflow (blueprint) that the WorkflowRun will reference
        workflow = Workflow(
            id=uuid.uuid4(),
            tenant_id="test-tenant",
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        integration_test_session.add(workflow)
        await integration_test_session.flush()

        # Create a workflow run
        workflow_run = WorkflowRun(
            id=uuid.uuid4(),
            tenant_id="test-tenant",
            workflow_id=workflow.id,  # Reference the workflow we just created
            status="running",
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(workflow_run)
        await integration_test_session.flush()

        # Create a task run linked to the workflow
        task_run = TaskRun(
            id=uuid.uuid4(),
            tenant_id="test-tenant",
            task_id=None,  # No saved task, just workflow execution
            workflow_run_id=workflow_run.id,  # Link to workflow
            cy_script="print('workflow task')",  # Ad-hoc script
            status="running",
            started_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Query and verify the relationship
        stmt = select(TaskRun).where(TaskRun.id == task_run.id)
        result = await integration_test_session.execute(stmt)
        fetched_task_run = result.scalar_one()

        assert fetched_task_run.workflow_run_id == workflow_run.id
        assert fetched_task_run.cy_script == "print('workflow task')"

        # Verify we can query task runs by workflow_run_id
        stmt = select(TaskRun).where(TaskRun.workflow_run_id == workflow_run.id)
        result = await integration_test_session.execute(stmt)
        workflow_tasks = result.scalars().all()

        assert len(workflow_tasks) == 1
        assert workflow_tasks[0].id == task_run.id

    @pytest.mark.asyncio
    async def test_task_run_without_workflow(
        self, integration_test_session: AsyncSession
    ):
        """Test TaskRun without a workflow (ad-hoc execution)."""
        # Create a task run without workflow_run_id
        task_run = TaskRun(
            id=uuid.uuid4(),
            tenant_id="test-tenant",
            task_id=None,  # Ad-hoc execution
            workflow_run_id=None,  # No workflow
            cy_script="print('hello')",
            status="running",
            started_at=datetime.now(UTC),
        )
        integration_test_session.add(task_run)
        await integration_test_session.commit()

        # Query and verify
        stmt = select(TaskRun).where(TaskRun.id == task_run.id)
        result = await integration_test_session.execute(stmt)
        fetched_task_run = result.scalar_one()

        assert fetched_task_run.workflow_run_id is None
        assert fetched_task_run.cy_script == "print('hello')"

    @pytest.mark.asyncio
    async def test_workflow_with_multiple_tasks(
        self, integration_test_session: AsyncSession
    ):
        """Test WorkflowRun with multiple TaskRuns."""
        # First create a Workflow (blueprint)
        workflow = Workflow(
            id=uuid.uuid4(),
            tenant_id="test-tenant",
            name="Test Multi-Task Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=str(SYSTEM_USER_ID),
        )
        integration_test_session.add(workflow)
        await integration_test_session.flush()

        # Create a workflow run
        workflow_run = WorkflowRun(
            id=uuid.uuid4(),
            tenant_id="test-tenant",
            workflow_id=workflow.id,
            status="running",
            created_at=datetime.now(UTC),
        )
        integration_test_session.add(workflow_run)
        await integration_test_session.flush()

        # Create multiple task runs for the workflow
        task_runs = []
        for i in range(3):
            task_run = TaskRun(
                id=uuid.uuid4(),
                tenant_id="test-tenant",
                task_id=None,  # No saved task
                workflow_run_id=workflow_run.id,
                cy_script=f"print('task {i}')",  # Ad-hoc script
                status="completed",
                started_at=datetime.now(UTC),
            )
            integration_test_session.add(task_run)
            task_runs.append(task_run)

        await integration_test_session.commit()

        # Query task runs by workflow_run_id
        stmt = select(TaskRun).where(TaskRun.workflow_run_id == workflow_run.id)
        result = await integration_test_session.execute(stmt)
        workflow_tasks = result.scalars().all()

        # Should have all 3 task runs
        assert len(workflow_tasks) == 3
        task_run_ids = {tr.id for tr in workflow_tasks}
        expected_ids = {tr.id for tr in task_runs}
        assert task_run_ids == expected_ids
