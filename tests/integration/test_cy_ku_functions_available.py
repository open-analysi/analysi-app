"""
Simple test to verify KU functions are available in Cy scripts.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.task_execution import DefaultTaskExecutor


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyKUFunctionsAvailable:
    """Verify KU functions are available to Cy scripts."""

    @pytest.mark.asyncio
    async def test_ku_functions_available_in_cy_execution(
        self, integration_test_session: AsyncSession
    ):
        """Test that all 6 KU functions are available in Cy scripts."""
        tenant_id = "cy-funcs-test"

        # Create test data
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        table = await ku_repo.create_table_ku(
            tenant_id,
            {
                "name": "TestTable",
                "description": "Test",
                "content": {"rows": [{"id": 1, "data": "test"}]},
                "row_count": 1,
                "column_count": 2,
            },
        )

        doc = await ku_repo.create_document_ku(
            tenant_id,
            {
                "name": "TestDoc",
                "description": "Test",
                "content": "Document content",
                "doc_format": "text",
            },
        )
        await integration_test_session.commit()

        # Cy script that tests all 6 functions
        cy_script = f"""
# Test each KU function is available
results = {{}}

# 1. table_read
table_data = table_read("TestTable")
results["table_read"] = len(table_data) > 0

# 2. table_read_via_id
table_by_id = table_read_via_id("{table.component_id!s}")
results["table_read_via_id"] = len(table_by_id) > 0

# 3. table_write
write_ok = table_write("TestTable", [{{"id": 2}}], "append")
results["table_write"] = write_ok

# 4. table_write_via_id
write_id_ok = table_write_via_id("{table.component_id!s}", [{{"id": 3}}], "append")
results["table_write_via_id"] = write_id_ok

# 5. document_read
doc_content = document_read("TestDoc")
results["document_read"] = len(doc_content) > 0

# 6. document_read_via_id
doc_by_id = document_read_via_id("{doc.component_id!s}")
results["document_read_via_id"] = len(doc_by_id) > 0

return results
"""

        # Execute with proper context
        executor = DefaultTaskExecutor()
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
        assert result["status"] == "completed", (
            f"Execution failed: {result.get('error', 'unknown error')}"
        )

        # Parse output if string
        output = result["output"]
        if isinstance(output, str):
            import ast

            output = ast.literal_eval(output)

        # Verify ALL 6 functions worked
        assert output["table_read"] is True, "table_read function not available"
        assert output["table_read_via_id"] is True, (
            "table_read_via_id function not available"
        )
        assert output["table_write"] is True, "table_write function not available"
        assert output["table_write_via_id"] is True, (
            "table_write_via_id function not available"
        )
        assert output["document_read"] is True, "document_read function not available"
        assert output["document_read_via_id"] is True, (
            "document_read_via_id function not available"
        )

        print("✅ All 6 KU functions are available and working in Cy scripts!")
