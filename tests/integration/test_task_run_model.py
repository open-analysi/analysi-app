"""
Database Schema Tests

Tests for task_runs table partitioning and Component field additions.
These tests should FAIL initially since the functionality isn't implemented yet (TDD).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from analysi.models.task_run import TaskRun  # Will be created


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunsTablePartitioning:
    """Test task_runs table creation with daily partitioning."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_task_runs_table_exists_with_partitioning(
        self, integration_test_session
    ):
        """Test that task_runs table exists and is partitioned by created_at."""
        session = integration_test_session
        # Check if task_runs table exists
        result = await session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'task_runs'
            );
        """
            )
        )
        table_exists = result.scalar()
        assert table_exists, "task_runs table should exist"

        # Check if it's partitioned
        result = await session.execute(
            text(
                """
            SELECT partrelid::regclass::text as partition_name
            FROM pg_partitioned_table
            WHERE partrelid = 'task_runs'::regclass;
        """
            )
        )
        partition_info = result.fetchone()
        assert partition_info is not None, "task_runs table should be partitioned"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_daily_partition_creation(self, integration_test_session):
        """Test that a daily partition exists for task_runs (created by pg_partman).

        pg_partman creates partitions with _pYYYYMMDD or _pYYYY_MM_DD naming.
        This test verifies pg_partman has created a partition covering today,
        rather than attempting to create one manually (which would conflict).
        """
        session = integration_test_session
        today = datetime.now(tz=UTC).date()

        # Query pg_inherits to find child partitions of task_runs covering today.
        # Matches both old format (_YYYY_MM_DD) and pg_partman format (_pYYYYMMDD).
        result = await session.execute(
            text(
                """
            SELECT c.relname FROM pg_catalog.pg_inherits i
            JOIN pg_catalog.pg_class c ON i.inhrelid = c.oid
            JOIN pg_catalog.pg_class p ON i.inhparent = p.oid
            WHERE p.relname = 'task_runs'
              AND c.relname LIKE :pattern
        """
            ),
            {"pattern": f"task_runs%{today.strftime('%Y%m%d')}%"},
        )
        partition_name = result.scalar()
        assert partition_name is not None, (
            f"A task_runs partition covering {today} should exist (created by pg_partman)"
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestComponentFieldAdditions:
    """Test Component table gets new fields."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_component_table_has_new_fields(self, integration_test_session):
        """Test that Component table includes created_by, version, last_used_at, system_only."""
        session = integration_test_session
        # Check for created_by field
        result = await session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'components'
                AND column_name = 'created_by'
            );
        """
            )
        )
        assert result.scalar(), "Component table should have created_by field"

        # Check for version field
        result = await session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'components'
                AND column_name = 'version'
            );
        """
            )
        )
        assert result.scalar(), "Component table should have version field"

        # Check for last_used_at field
        result = await session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'components'
                AND column_name = 'last_used_at'
            );
        """
            )
        )
        assert result.scalar(), "Component table should have last_used_at field"

        # Check for system_only field
        result = await session.execute(
            text(
                """
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'components'
                AND column_name = 'system_only'
            );
        """
            )
        )
        assert result.scalar(), "Component table should have system_only field"


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunModelCRUD:
    """Test TaskRun model CRUD operations work correctly."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_task_run_model_creation(self, integration_test_session):
        """Test that TaskRun model can be created with all spec v2 fields."""
        session = integration_test_session
        # This will fail until TaskRun model is implemented
        task_run = TaskRun(
            tenant_id="test_tenant",
            task_id=None,  # Ad-hoc execution
            cy_script="return 'Hello World'",
            status="running",
            input_type="inline",
            input_location="{'message': 'test input'}",
            input_content_type="application/json",
            output_type="inline",
            output_location=None,
            output_content_type=None,
            executor_config={"executor_type": "default", "timeout_seconds": 30},
            execution_context={"available_tools": [], "llm_model": "gpt-4"},
        )

        session.add(task_run)
        await session.commit()
        await session.refresh(task_run)

        assert task_run.id is not None
        assert task_run.tenant_id == "test_tenant"
        assert task_run.status == "running"
        assert task_run.created_at is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_task_run_status_transitions(self, integration_test_session):
        """Test that TaskRun status can be updated through transitions."""
        session = integration_test_session
        # Create initial task run
        task_run = TaskRun(
            tenant_id="test_tenant", cy_script="return 'test'", status="running"
        )

        session.add(task_run)
        await session.commit()
        await session.refresh(task_run)

        # Update status to succeeded
        task_run.status = "completed"
        task_run.completed_at = datetime.now(UTC)
        task_run.output_location = "{'result': 'test'}"
        task_run.output_content_type = "application/json"

        await session.commit()
        await session.refresh(task_run)

        assert task_run.status == "completed"
        assert task_run.completed_at is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestPartitionAwareQueries:
    """Test partition-aware queries return correct data."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partition_aware_task_run_queries(self, integration_test_session):
        """Test that queries work correctly across partitions."""
        session = integration_test_session
        # Create task runs in different time periods
        today_task = TaskRun(
            tenant_id="test_tenant",
            cy_script="return 'today'",
            status="completed",
            created_at=datetime.now(UTC),
        )

        session.add(today_task)
        await session.commit()
        await session.refresh(today_task)

        # Query by tenant should work across partitions
        result = await session.execute(
            text(
                """
            SELECT COUNT(*) FROM task_runs
            WHERE tenant_id = 'test_tenant'
        """
            )
        )
        count = result.scalar()
        assert count >= 1, "Should find task runs by tenant across partitions"

        # Query by status should work across partitions
        result = await session.execute(
            text(
                """
            SELECT COUNT(*) FROM task_runs
            WHERE status = 'completed'
        """
            )
        )
        count = result.scalar()
        assert count >= 1, "Should find task runs by status across partitions"
