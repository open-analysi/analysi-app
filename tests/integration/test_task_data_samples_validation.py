"""
Integration test for Finding #6: Task Data Samples Validation.

Tests that task data_samples duck-type match what the script actually uses.
This prevents tasks from being created with mismatched schemas that would
fail later during workflow validation.

TDD Approach:
1. Write test that expects validation to catch data_samples mismatch (FAIL)
2. Implement validation logic (PASS)
3. Verify workflows work with properly validated tasks (PASS)
"""

import pytest

from analysi.models.task import Task
from analysi.schemas.task import TaskCreate
from analysi.services.task import TaskService
from analysi.services.type_propagation.errors import TypePropagationError
from analysi.services.type_propagation.task_inference import infer_task_output_schema


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskDataSamplesValidation:
    """Test that task data_samples are validated against script expectations."""

    @pytest.mark.asyncio
    async def test_task_with_mismatched_data_samples_still_creates(
        self, integration_test_session, sample_tenant_id
    ):
        """
        Test that creating a task with mismatched data_samples does NOT block creation.

        The type checker uses strict_input=False for data_samples validation, which
        means accessing undefined fields is permissive. This avoids false positives
        with ?? (null coalesce) and dynamic dict patterns.
        """
        service = TaskService(integration_test_session)

        # Create task with MISMATCHED data_samples
        task_data = TaskCreate(
            name="IP Analysis (Bad Data Samples)",
            description="Task with mismatched data samples",
            script="""
# Script expects input["ip"] and input["context"]
ip_address = input["ip"]
context = input["context"]

return {
    "ip": ip_address,
    "context": context
}
""",
            function="search",
            scope="processing",
            # Data samples don't match! Provides "input_data" instead of "ip" and "context"
            data_samples=[
                {"input_data": {"ip": "8.8.8.8", "context": "firewall_alert"}}
            ],
        )

        # Task creation succeeds - data_samples validation is non-strict
        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        assert task is not None
        assert task.data_samples is not None

    @pytest.mark.asyncio
    async def test_task_with_correct_data_samples_passes_validation(
        self, integration_test_session, sample_tenant_id
    ):
        """
        Test that creating a task with data_samples that match script succeeds.

        Script expects: input["ip"] and input["context"]
        Data samples provide: exactly that structure

        Expected: Validation should pass
        """
        service = TaskService(integration_test_session)

        # Create task with CORRECT data_samples
        task_data = TaskCreate(
            name="IP Analysis (Good Data Samples)",
            description="Task with correct data samples",
            script="""
# Script expects input["ip"] and input["context"]
ip_address = input["ip"]
context = input["context"]

return {
    "ip": ip_address,
    "context": context
}
""",
            function="search",
            scope="processing",
            # Data samples MATCH! Provides exactly what script expects
            data_samples=[{"ip": "8.8.8.8", "context": "firewall_alert"}],
        )

        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        # Validate the task - should succeed
        if task.data_samples:
            sample_input = task.data_samples[0]

            # Try to infer output schema using the data sample
            result = await infer_task_output_schema(
                Task(
                    component_id=task.component_id,
                    script=task.script,
                    function=task.function,
                ),
                sample_input,
            )

            # Should NOT be an error
            assert not isinstance(result, TypePropagationError), (
                f"Expected successful validation, but got error: {result.message if isinstance(result, TypePropagationError) else result}"
            )

            # Should return valid schema
            assert "type" in result, f"Expected schema with 'type', got: {result}"

    @pytest.mark.asyncio
    async def test_task_create_succeeds_with_mismatched_data_samples(
        self, integration_test_session, sample_tenant_id
    ):
        """
        Test that TaskService.create_task succeeds even when data_samples
        don't match script expectations.

        The type checker uses strict_input=False for data_samples, so field
        mismatches are permissive (avoids false positives with ?? and dynamic dicts).
        """
        service = TaskService(integration_test_session)

        # Try to create task with mismatched data_samples
        task_data = TaskCreate(
            name="Invalid Task",
            description="Should still create successfully",
            script="""
ip = input["ip"]
return {"result": ip}
""",
            function="search",
            scope="processing",
            data_samples=[
                {
                    "wrong_field": "8.8.8.8"  # Script expects "ip", not "wrong_field"
                }
            ],
        )

        # Task creation succeeds - data_samples validation is non-strict
        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        assert task is not None
        assert task.data_samples == [{"wrong_field": "8.8.8.8"}]

    @pytest.mark.asyncio
    async def test_workflow_validation_with_proper_input_schema(
        self, integration_test_session, sample_tenant_id
    ):
        """
        Test that workflow validation uses io_schema.input, not task data_samples.

        This is the fix for the workflow creation issue:
        - Workflow provides io_schema.input = {"ip": string, "context": string}
        - Task expects input["ip"] and input["context"]
        - Validation should use workflow's input schema, not task's data_samples

        Expected: Workflow validates successfully when schemas match
        """
        service = TaskService(integration_test_session)

        # Create task with correct script (expects ip and context)
        task_data = TaskCreate(
            name="IP Analysis for Workflow",
            description="Task for workflow validation test",
            script="""
ip_address = input["ip"]
context = input["context"]

return {
    "analysis": "IP ${ip_address} in context ${context}",
    "ip": ip_address
}
""",
            function="search",
            scope="processing",
            # Task's data_samples for standalone testing
            data_samples=[{"ip": "1.2.3.4", "context": "test"}],
        )

        task = await service.create_task(sample_tenant_id, task_data)
        await integration_test_session.commit()

        # Now validate with WORKFLOW's input schema (not task's data_samples)
        workflow_input_schema = {
            "type": "object",
            "properties": {"ip": {"type": "string"}, "context": {"type": "string"}},
            "required": ["ip", "context"],
        }

        # Validate task with workflow's input schema
        result = await infer_task_output_schema(
            Task(
                component_id=task.component_id,
                script=task.script,
                function=task.function,
            ),
            workflow_input_schema,  # Use workflow's schema, not task's data_samples!
        )

        # Should succeed because schemas match
        assert not isinstance(result, TypePropagationError), (
            f"Validation should succeed with matching workflow schema, but got: {result.message if isinstance(result, TypePropagationError) else result}"
        )

        assert result.get("type") == "object", (
            f"Expected object output type, got: {result}"
        )
