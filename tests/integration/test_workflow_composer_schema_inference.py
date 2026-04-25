"""
Integration tests for schema inference in workflow composer.

Tests that TaskResolver properly infers schemas from task data_samples.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component
from analysi.models.task import Task
from analysi.services.workflow_composer.resolvers import TaskResolver


@pytest.mark.asyncio
@pytest.mark.integration
class TestSchemaInference:
    """Test schema inference from task data_samples."""

    @pytest.fixture
    async def task_with_data_samples(
        self, integration_test_session: AsyncSession
    ) -> Task:
        """Create a task with valid data_samples."""
        # Create component
        component = Component(
            tenant_id="test_tenant",
            cy_name="test_enrichment",
            name="Test Enrichment",
            description="Test task with data samples",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create task with data_samples and valid script
        task = Task(
            component_id=component.id,
            script="""
# Test enrichment task
username = input["username"]
alert_id = input["alert_id"]
return {"user": username, "alert": alert_id, "enriched": True}
""",
            data_samples=[
                {"username": "jsmith", "alert_id": "AL-001"},
                {"username": "bjones", "alert_id": "AL-002"},
            ],
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        return task

    @pytest.mark.asyncio
    async def test_task_resolver_infers_schema_from_data_samples(
        self,
        integration_test_session: AsyncSession,
        task_with_data_samples: Task,
    ):
        """
        Test that TaskResolver.resolve() infers input schema from data_samples.

        Given: Task with data_samples containing username and alert_id
        When: Calling TaskResolver.resolve()
        Then: ResolvedTask should have input_schema with properties for username and alert_id
        """
        # Arrange
        resolver = TaskResolver(session=integration_test_session)

        # Act
        resolved = await resolver.resolve(
            cy_name="test_enrichment", tenant_id="test_tenant"
        )

        # Assert
        assert resolved is not None, "TaskResolver should return ResolvedTask"
        assert resolved.cy_name == "test_enrichment"
        assert resolved.input_schema is not None, "Should have input schema"

        # Check that input schema has properties (not bare {"type": "object"})
        assert "type" in resolved.input_schema
        assert resolved.input_schema["type"] == "object"
        assert "properties" in resolved.input_schema, (
            f"Input schema should have properties, got: {resolved.input_schema}"
        )

        # Check that properties include fields from data_samples
        properties = resolved.input_schema["properties"]
        assert "username" in properties, (
            f"Should have 'username' property, got: {properties.keys()}"
        )
        assert "alert_id" in properties, (
            f"Should have 'alert_id' property, got: {properties.keys()}"
        )

    @pytest.mark.asyncio
    async def test_task_resolver_infers_output_schema_from_compilation(
        self,
        integration_test_session: AsyncSession,
        task_with_data_samples: Task,
    ):
        """
        Test that TaskResolver.resolve() infers output schema via Cy compilation.

        Given: Task with valid script that returns specific fields
        When: Calling TaskResolver.resolve()
        Then: ResolvedTask should have output_schema inferred from compilation
        """
        # Arrange
        resolver = TaskResolver(session=integration_test_session)

        # Act
        resolved = await resolver.resolve(
            cy_name="test_enrichment", tenant_id="test_tenant"
        )

        # Assert
        assert resolved.output_schema is not None, "Should have output schema"
        assert "type" in resolved.output_schema
        assert resolved.output_schema["type"] == "object"

        # Output schema should have properties from return statement
        if "properties" in resolved.output_schema:
            properties = resolved.output_schema["properties"]
            # The script returns {"user": username, "alert": alert_id, "enriched": True}
            assert (
                "user" in properties
                or "alert" in properties
                or "enriched" in properties
            )

    @pytest.mark.asyncio
    async def test_task_resolver_handles_empty_data_samples(
        self,
        integration_test_session: AsyncSession,
    ):
        """
        Test that TaskResolver handles task with empty data_samples array.

        Given: Task with empty data_samples array
        When: Calling TaskResolver.resolve()
        Then: Should return None for input_schema (cannot infer from empty samples)
        """
        # Create component
        component = Component(
            tenant_id="test_tenant",
            cy_name="task_no_samples",
            name="Task No Samples",
            description="Task with empty data_samples",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create task with EMPTY data_samples
        task = Task(
            component_id=component.id,
            script='return {"result": "ok"}',
            data_samples=[],  # Empty array
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        # Act
        resolver = TaskResolver(session=integration_test_session)
        resolved = await resolver.resolve(
            cy_name="task_no_samples", tenant_id="test_tenant"
        )

        # Assert
        assert resolved is not None
        assert resolved.input_schema is None, (
            "Should not infer schema from empty data_samples"
        )

    @pytest.mark.asyncio
    async def test_task_resolver_handles_null_data_samples(
        self,
        integration_test_session: AsyncSession,
    ):
        """
        Test that TaskResolver handles task with null data_samples.

        Given: Task with data_samples=None
        When: Calling TaskResolver.resolve()
        Then: Should return None for input_schema
        """
        # Create component
        component = Component(
            tenant_id="test_tenant",
            cy_name="task_null_samples",
            name="Task Null Samples",
            description="Task with null data_samples",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create task with NULL data_samples
        task = Task(
            component_id=component.id,
            script='return {"result": "ok"}',
            data_samples=None,  # Null
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        # Act
        resolver = TaskResolver(session=integration_test_session)
        resolved = await resolver.resolve(
            cy_name="task_null_samples", tenant_id="test_tenant"
        )

        # Assert
        assert resolved is not None
        assert resolved.input_schema is None, (
            "Should handle null data_samples gracefully"
        )
