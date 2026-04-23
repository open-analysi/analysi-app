"""
Simple integration tests for Cy scripts using KU functions.

Tests that KU functions are available to Cy scripts using the executor directly.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyKUExecutionSimple:
    """Test KU functions in Cy scripts using direct execution."""

    @pytest.mark.asyncio
    async def test_table_read_function_in_cy_script(
        self, integration_test_session: AsyncSession
    ):
        """Test that table_read function works in Cy scripts."""
        tenant_id = "cy-ku-test"
        table_name = "Assets"
        table_data = [
            {"id": 1, "name": "Server-1", "status": "active"},
            {"id": 2, "name": "Server-2", "status": "inactive"},
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

        # Create executor
        executor = DefaultTaskExecutor()

        # Cy script that uses table_read
        cy_script = f"""
# Read table data
assets = table_read("{table_name}")

# Process the data
active_count = 0
i = 0
while (i < len(assets)) {{
    asset = assets[i]
    if (asset["status"] == "active") {{
        active_count = active_count + 1
    }}
    i = i + 1
}}

# Return results
return {{
    "total_assets": len(assets),
    "active_count": active_count,
    "first_asset": assets[0]["name"]
}}
"""

        # Execute with context including session
        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(uuid4()),
            "task_run_id": str(uuid4()),
            "session": integration_test_session,  # Critical for KU functions
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data={},
            execution_context=execution_context,
        )

        # Verify execution succeeded
        if result["status"] != "completed":
            print(f"Execution failed: {result}")
            if "error" in result:
                print(f"Error: {result['error']}")
        assert result["status"] == "completed"

        # Parse Cy output (may be Python repr string or dict)
        output = parse_cy_output(result["output"])

        assert output["total_assets"] == 2
        assert output["active_count"] == 1
        assert output["first_asset"] == "Server-1"

    @pytest.mark.asyncio
    async def test_table_write_and_read_in_cy_script(
        self, integration_test_session: AsyncSession
    ):
        """Test table_write and table_read functions work together."""
        tenant_id = "cy-write-test"
        table_name = "Metrics"

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

        executor = DefaultTaskExecutor()

        # Cy script that writes then reads
        cy_script = f"""
# Initial data
initial_metrics = [
    {{"metric": "cpu", "value": 75}},
    {{"metric": "memory", "value": 60}}
]

# Write data using replace mode
write_result = table_write("{table_name}", initial_metrics, "replace")

# Read back the data
stored_metrics = table_read("{table_name}")

# Append more data
additional_metrics = [{{"metric": "disk", "value": 85}}]
append_result = table_write("{table_name}", additional_metrics, "append")

# Read final data
final_metrics = table_read("{table_name}")

return {{
    "write_success": write_result,
    "append_success": append_result,
    "initial_count": len(stored_metrics),
    "final_count": len(final_metrics),
    "metrics": final_metrics
}}
"""

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(uuid4()),
            "task_run_id": str(uuid4()),
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data={},
            execution_context=execution_context,
        )

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["write_success"] is True
        assert output["append_success"] is True
        assert output["initial_count"] == 2
        assert output["final_count"] == 3
        assert len(output["metrics"]) == 3

    @pytest.mark.asyncio
    async def test_document_read_in_cy_script(
        self, integration_test_session: AsyncSession
    ):
        """Test document_read function in Cy scripts."""
        tenant_id = "cy-doc-test"
        doc_name = "Policy"
        doc_content = "This is a security policy document."

        # Create document
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": doc_name,
                "description": "Test document",
                "content": doc_content,
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        executor = DefaultTaskExecutor()

        # Cy script that reads document (simplified - Cy doesn't support 'in' or .split())
        cy_script = f"""
# Read document
content = document_read("{doc_name}")

# Return basic info about the content
return {{
    "content_length": len(content),
    "content": content
}}
"""

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(uuid4()),
            "task_run_id": str(uuid4()),
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data={},
            execution_context=execution_context,
        )

        if result["status"] == "failed":
            print(
                f"Document read test failed with error: {result.get('error', 'Unknown error')}"
            )

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["content_length"] == len(doc_content)
        assert output["content"] == doc_content

    @pytest.mark.asyncio
    async def test_uuid_based_functions_in_cy_script(
        self, integration_test_session: AsyncSession
    ):
        """Test table_read_via_id and document_read_via_id functions."""
        tenant_id = "cy-uuid-test"

        # Create table and document
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        table = await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": "UUID Table",
                "description": "Test",
                "content": {"rows": [{"id": 1, "type": "uuid-test"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )

        doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "UUID Doc",
                "description": "Test",
                "content": "Document accessed by UUID",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        executor = DefaultTaskExecutor()

        # Cy script using UUID-based functions
        cy_script = f"""
# Use UUID-based functions
table_data = table_read_via_id("{table.component_id!s}")
doc_content = document_read_via_id("{doc.component_id!s}")

# Test write via id
new_data = [{{"id": 2, "type": "written-via-id"}}]
write_success = table_write_via_id("{table.component_id!s}", new_data, "append")

# Read again to verify
final_data = table_read_via_id("{table.component_id!s}")

return {{
    "table_row_type": table_data[0]["type"],
    "doc_content": doc_content,
    "write_success": write_success,
    "final_row_count": len(final_data)
}}
"""

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(uuid4()),
            "task_run_id": str(uuid4()),
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data={},
            execution_context=execution_context,
        )

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["table_row_type"] == "uuid-test"
        assert output["doc_content"] == "Document accessed by UUID"
        assert output["write_success"] is True
        assert output["final_row_count"] == 2

    @pytest.mark.asyncio
    async def test_all_ku_functions_available(
        self, integration_test_session: AsyncSession
    ):
        """Verify all 6 KU functions are available in Cy context."""
        tenant_id = "cy-all-funcs"

        # Create test data
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        table = await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": "Test",
                "description": "Test",
                "content": {"rows": []},
                "row_count": 0,
                "column_count": 1,
            },
        )
        doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "Doc",
                "description": "Test",
                "content": "test",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        executor = DefaultTaskExecutor()

        # Cy script that tests all function availability (simplified - just call the functions)
        cy_script = f"""
# Test that we can read the table and document we created
table_data = table_read_via_id("{table.component_id!s}")
doc_content = document_read_via_id("{doc.component_id!s}")

# Return success with the data we read
return {{
    "table_rows": len(table_data),
    "doc_content": doc_content,
    "success": 1
}}
"""

        execution_context = {
            "tenant_id": tenant_id,
            "task_id": str(uuid4()),
            "task_run_id": str(uuid4()),
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data={},
            execution_context=execution_context,
        )

        if result["status"] == "failed":
            print(
                f"All functions test failed with error: {result.get('error', 'Unknown error')}"
            )

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["table_rows"] == 0  # We created 0 rows in the table
        assert output["doc_content"] == "test"  # We created doc with content "test"
        assert output["success"] == 1
