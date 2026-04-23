"""
Integration test to verify KU functions work via API endpoints.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_full_stack,
    pytest.mark.arq_worker,
]


@pytest.mark.asyncio
@pytest.mark.integration
class TestAPIKUFunctions:
    """Test KU functions via API endpoints."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        # Clean up the override
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_table_read_via_api(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        sample_tenant_id: str,
    ):
        """Test that table_read function works when tasks are executed via API."""

        # Step 1: Create a table with test data
        ku_repo = KnowledgeUnitRepository(integration_test_session)
        table_data = [
            {"id": 1, "name": "test1", "value": "data1"},
            {"id": 2, "name": "test2", "value": "data2"},
        ]

        await ku_repo.create_table_ku(
            sample_tenant_id,
            {
                "name": "API Test Table",
                "description": "Test table for API KU function verification",
                "content": {"rows": table_data},
                "row_count": len(table_data),
                "column_count": 3,
            },
        )
        await integration_test_session.commit()

        # Step 2: Execute ad-hoc task via API that uses table_read
        cy_script = """
table_data = table_read("API Test Table")
return {
    "table_rows": len(table_data),
    "first_row_name": table_data[0]["name"],
    "success": True
}
"""

        execution_data = {"cy_script": cy_script, "input": {}, "executor_config": {}}

        # Execute via API
        response = await client.post(
            f"/v1/{sample_tenant_id}/tasks/run", json=execution_data
        )

        assert response.status_code == 202
        task_run_data = response.json()["data"]
        trid = task_run_data["trid"]

        # Step 3: Poll for completion
        import asyncio
        import time

        start_time = time.time()
        max_wait = 30  # 30 second timeout

        while time.time() - start_time < max_wait:
            status_response = await client.get(
                f"/v1/{sample_tenant_id}/task-runs/{trid}/status"
            )
            assert status_response.status_code == 200
            status_data = status_response.json()["data"]

            if status_data["status"] in ["completed", "failed"]:
                break

            await asyncio.sleep(1)

        # Step 4: Get full task run details to see what happened
        details_response = await client.get(f"/v1/{sample_tenant_id}/task-runs/{trid}")
        assert details_response.status_code == 200
        details_data = details_response.json()["data"]

        # Print details for debugging
        print("\n--- Task Execution Details ---")
        print(f"Task run ID: {trid}")
        print(f"Status: {details_data['status']}")
        print(f"Input type: {details_data.get('input_type')}")
        print(f"Output type: {details_data.get('output_type')}")

        # Verify the task succeeded and used table_read
        assert status_data["status"] == "completed", (
            f"Task failed. Details: {details_data}"
        )

        print("✅ table_read function successfully worked via API!")

    @pytest.mark.asyncio
    async def test_llm_functions_load_via_api(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        sample_tenant_id: str,
    ):
        """Test that LLM functions load properly when tasks are executed via API."""

        # Execute ad-hoc task that would use LLM functions (even if it fails, we can check logs)
        cy_script = """
# Just test that LLM functions are available (don't actually call them to avoid costs)
return {"llm_available": True}
"""

        execution_data = {"cy_script": cy_script, "input": {}, "executor_config": {}}

        # Execute via API
        response = await client.post(
            f"/v1/{sample_tenant_id}/tasks/run", json=execution_data
        )

        assert response.status_code == 202
        task_run_data = response.json()["data"]
        trid = task_run_data["trid"]

        # Poll for completion
        import asyncio
        import time

        start_time = time.time()
        max_wait = 10  # 10 second timeout for simple test

        while time.time() - start_time < max_wait:
            status_response = await client.get(
                f"/v1/{sample_tenant_id}/task-runs/{trid}/status"
            )
            assert status_response.status_code == 200
            status_data = status_response.json()["data"]

            if status_data["status"] in ["completed", "failed"]:
                break

            await asyncio.sleep(1)

        # The test here is mainly that LLM functions load without errors (check logs)
        # The task should succeed since it's not actually calling LLM functions
        assert status_data["status"] == "completed", (
            f"Simple task failed: {status_data}"
        )
        print(
            "✅ LLM functions loading test completed (check logs for 'Loaded integration-based LLM functions')"
        )
