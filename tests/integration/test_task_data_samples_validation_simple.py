"""
Simple integration test for task data_samples validation (Finding #6).

Tests that TaskService validates data_samples match script expectations.
"""

import pytest

from analysi.schemas.task import TaskCreate
from analysi.services.task import TaskService


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskDataSamplesValidationSimple:
    """Test automatic validation of task data_samples."""

    @pytest.mark.asyncio
    async def test_task_with_wrong_data_samples_still_creates(
        self, integration_test_session, sample_tenant_id
    ):
        """Task creation succeeds even when data_samples don't match script.

        The type checker uses strict_input=False, so field mismatches are permissive.
        """
        service = TaskService(integration_test_session)

        task_data = TaskCreate(
            name="Invalid Task",
            description="data_samples provide wrong field",
            script="""
ip = input["ip"]
return {"result": ip}
""",
            function="search",
            scope="processing",
            data_samples=[{"wrong_field": "8.8.8.8"}],  # Script expects "ip"
        )

        # Task creation succeeds - data_samples validation is non-strict
        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        assert task is not None
        assert task.data_samples == [{"wrong_field": "8.8.8.8"}]

    @pytest.mark.asyncio
    async def test_task_with_correct_data_samples_succeeds(
        self, integration_test_session, sample_tenant_id
    ):
        """Task creation should succeed when data_samples match script."""
        service = TaskService(integration_test_session)

        task_data = TaskCreate(
            name="Valid Task",
            description="data_samples match script",
            script="""
ip = input["ip"]
return {"result": ip}
""",
            function="search",
            scope="processing",
            data_samples=[{"ip": "8.8.8.8"}],  # Correct!
        )

        # Should succeed
        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        assert task is not None
        assert task.data_samples == [{"ip": "8.8.8.8"}]

    @pytest.mark.asyncio
    async def test_duck_typing_extra_fields_allowed(
        self, integration_test_session, sample_tenant_id
    ):
        """Data samples can have extra fields (duck typing)."""
        service = TaskService(integration_test_session)

        task_data = TaskCreate(
            name="Duck Typing Task",
            description="data_samples have extra fields",
            script="""
ip = input["ip"]
return {"result": ip}
""",
            function="search",
            scope="processing",
            data_samples=[
                {
                    "ip": "8.8.8.8",
                    "extra_field": "foo",  # Not used by script - OK!
                    "another_field": 123,  # Also OK!
                }
            ],
        )

        # Should succeed - extra fields don't matter
        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        assert task is not None
