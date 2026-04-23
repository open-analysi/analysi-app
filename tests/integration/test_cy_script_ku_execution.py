"""
Integration tests for actual Cy script execution with KU functions.

These tests execute REAL Cy scripts through the task execution service.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import TaskExecutionService
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyScriptKUExecution:
    """Test actual Cy script execution with KU functions."""

    @pytest.mark.asyncio
    async def test_cy_script_table_read_by_name(
        self, integration_test_session: AsyncSession
    ):
        """Execute a real Cy script that reads a table by name."""
        tenant_id = "cy-test-tenant"
        table_name = "Asset Inventory"
        table_data = [
            {"id": 1, "asset": "Server-A", "location": "DC1"},
            {"id": 2, "asset": "Server-B", "location": "DC2"},
        ]

        # Create table
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Test assets",
                "content": {"rows": table_data},
                "row_count": len(table_data),
                "column_count": 3,
            },
        )
        await integration_test_session.commit()

        # Create a task with Cy script that reads the table
        task_repo = TaskRepository(integration_test_session)
        task = await task_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "Read Asset Table",
                "description": "Reads asset inventory table",
                "script": f'''
# Read the asset inventory table
assets = table_read("{table_name}")
return assets
''',
            }
        )
        await integration_test_session.commit()

        # Execute the task using current API
        from analysi.services.task_run import TaskRunService

        task_run_service = TaskRunService()
        exec_service = TaskExecutionService()

        # Create task run
        task_run = await task_run_service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component_id,
            cy_script=None,  # Will be loaded from task
            input_data={},
            executor_config=None,
        )
        await integration_test_session.commit()

        # Execute the task (creates its own session internally)
        result = await exec_service.execute_single_task(task_run.id, tenant_id)

        # Verify result
        assert result.status == "completed", (
            f"Task run status: {result.status}, error: {result.error_message}"
        )

        # Verify output data
        output_data = parse_cy_output(result.output_data)
        assert output_data == table_data

    @pytest.mark.asyncio
    async def test_cy_script_table_write_and_read(
        self, integration_test_session: AsyncSession
    ):
        """Execute a Cy script that writes to a table then reads it back."""
        tenant_id = "cy-test-tenant-2"
        table_name = "Metrics Table"

        # Create empty table
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": table_name,
                "description": "Metrics storage",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 2,
            },
        )
        await integration_test_session.commit()

        # Create task that writes then reads
        task_repo = TaskRepository(integration_test_session)
        task = await task_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "Write and Read Metrics",
                "description": "Write metrics then read them back",
                "script": f'''
# Prepare new metrics data
new_metrics = [
    {{"metric": "cpu_usage", "value": 85}},
    {{"metric": "memory_usage", "value": 72}}
]

# Write to table (replace mode)
success = table_write("{table_name}", new_metrics, "replace")

# Read back to verify
data = table_read("{table_name}")
return {{
    "write_success": success,
    "data_count": len(data),
    "data": data
}}
''',
            }
        )
        await integration_test_session.commit()

        # Execute the task using current API
        from analysi.services.task_run import TaskRunService

        task_run_service = TaskRunService()
        exec_service = TaskExecutionService()

        # Create task run
        task_run = await task_run_service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component_id,
            cy_script=None,  # Will be loaded from task
            input_data={},
            executor_config=None,
        )
        await integration_test_session.commit()

        # Execute the task (creates its own session internally)
        result = await exec_service.execute_single_task(task_run.id, tenant_id)

        # Verify result
        assert result.status == "completed", (
            f"Task run status: {result.status}, error: {result.error_message}"
        )

        # Verify output data
        output_data = parse_cy_output(result.output_data)
        assert output_data["write_success"] is True
        assert output_data["data_count"] == 2
        assert output_data["data"][0]["metric"] == "cpu_usage"

    @pytest.mark.asyncio
    async def test_cy_script_document_read(
        self, integration_test_session: AsyncSession
    ):
        """Execute a Cy script that reads a document."""
        tenant_id = "cy-test-tenant-3"
        doc_name = "Security Guidelines"
        doc_content = "This is our security policy document."

        # Create document
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": doc_name,
                "description": "Security doc",
                "content": doc_content,
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Create task that reads document
        task_repo = TaskRepository(integration_test_session)
        task = await task_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "Read Security Doc",
                "description": "Read security guidelines",
                "script": f'''
# Read the security document
content = document_read("{doc_name}")
# Simplified - just return the content and length
return {{
    "doc_length": len(content),
    "content": content
}}
''',
            }
        )
        await integration_test_session.commit()

        # Execute the task using current API
        from analysi.services.task_run import TaskRunService

        task_run_service = TaskRunService()
        exec_service = TaskExecutionService()

        # Create task run
        task_run = await task_run_service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component_id,
            cy_script=None,  # Will be loaded from task
            input_data={},
            executor_config=None,
        )
        await integration_test_session.commit()

        # Execute the task (creates its own session internally)
        result = await exec_service.execute_single_task(task_run.id, tenant_id)

        # Verify result
        assert result.status == "completed", (
            f"Task run status: {result.status}, error: {result.error_message}"
        )

        # Verify output data
        output_data = parse_cy_output(result.output_data)
        assert output_data["doc_length"] == len(doc_content)
        assert output_data["content"] == doc_content

    @pytest.mark.asyncio
    async def test_cy_script_function_signature_error(
        self, integration_test_session: AsyncSession
    ):
        """Test that Cy script fails with proper error when using wrong function signature."""
        tenant_id = "cy-test-tenant-4"

        # Create a task with incorrect Cy function call
        task_repo = TaskRepository(integration_test_session)
        task = await task_repo.create(
            {
                "tenant_id": tenant_id,
                "name": "Bad Function Call",
                "description": "Test incorrect function signature",
                "script": """
# This should fail - Cy doesn't support keyword arguments like this
data = table_read(name="SomeTable", max_rows=10)
return data
""",
            }
        )
        await integration_test_session.commit()

        # Execute the task - should fail
        from analysi.services.task_run import TaskRunService

        task_run_service = TaskRunService()
        exec_service = TaskExecutionService()

        # Create task run
        task_run = await task_run_service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=task.component_id,
            cy_script=None,  # Will be loaded from task
            input_data={},
            executor_config=None,
        )
        await integration_test_session.commit()

        # Execute the task (creates its own session internally)
        result = await exec_service.execute_single_task(task_run.id, tenant_id)

        # Should fail due to Cy not supporting keyword arguments
        assert result.status == "failed"
        # The error should mention the syntax issue with keyword arguments
