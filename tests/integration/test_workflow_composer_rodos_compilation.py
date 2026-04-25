"""
Integration tests for Workflow Composer Rodos Compilation (TDD).

Tests that compose_workflow compiles each task with the previous task's output
schema as input, catching compilation errors like missing return statements.

This is the core of Rodos: type-safe workflow composition via progressive
Cy compilation through the DAG.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.settings import settings
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.component import Component
from analysi.models.task import Task
from analysi.services.workflow_composer.service import WorkflowComposerService


@pytest.mark.asyncio
@pytest.mark.integration
class TestRodosCompilation:
    """Test that compose_workflow catches task compilation errors."""

    @pytest.fixture(autouse=True)
    def enable_type_validation(self, monkeypatch):
        """Enable type validation for all tests in this class."""
        # These tests require type validation to catch compilation/type errors
        monkeypatch.setattr(settings, "ENABLE_WORKFLOW_TYPE_VALIDATION", True)
        return

    @pytest.fixture
    async def task_with_compilation_error(
        self, integration_test_session: AsyncSession
    ) -> Task:
        """Create a task with missing return statement (compilation error)."""
        # Create component
        component = Component(
            tenant_id="test_tenant",
            cy_name="broken_task",
            name="Broken Task",
            description="Task missing return statement",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create task with NO return statement (should fail Cy compilation)
        task = Task(
            component_id=component.id,
            script="""
# This task has NO return statement - should fail compilation
username = input["username"]
output = {"processed": username}
# Missing: return output
""",
            data_samples=[{"username": "testuser"}],
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        return task

    @pytest.fixture
    async def valid_task(self, integration_test_session: AsyncSession) -> Task:
        """Create a valid task that expects processed field."""
        # Create component
        component = Component(
            tenant_id="test_tenant",
            cy_name="valid_task",
            name="Valid Task",
            description="Task that processes input",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create task with proper return
        task = Task(
            component_id=component.id,
            script="""
# Valid task
processed_value = input["processed"]
return {"result": processed_value + "_done"}
""",
            data_samples=[{"processed": "test"}],
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        return task

    @pytest.mark.asyncio
    async def test_compose_catches_missing_return_statement(
        self,
        integration_test_session: AsyncSession,
        task_with_compilation_error: Task,
        valid_task: Task,
    ):
        """
        Test that compose_workflow catches compilation errors via Cy compilation.

        Given:
        - Task 1 with missing return statement
        - Task 2 that's valid

        When:
        - Composing ["broken_task", "valid_task"]

        Then:
        - compose_workflow should return status="error"
        - Should have compilation error about missing return
        - Should NOT allow workflow creation
        """
        # Arrange
        composer = WorkflowComposerService(session=integration_test_session)

        # Act
        result = await composer.compose_workflow(
            composition=["broken_task", "valid_task"],
            workflow_name="Test Workflow",
            workflow_description="Should fail due to compilation error",
            tenant_id="test_tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,  # Just validate, don't create
        )

        # Assert
        assert result.status == "error", (
            "Expected compose_workflow to catch compilation error, "
            f"but got status={result.status}"
        )
        assert len(result.errors) > 0, "Expected compilation errors"

        # Check for compilation/syntax error
        error_types = [e.error_type for e in result.errors]
        error_messages = [e.message for e in result.errors]

        # Accept type_validation_error, syntax_error, or missing_required_field
        # (missing_required_field occurs when task has no return, so output is empty)
        assert any(
            t
            in [
                "syntax_error",
                "type_inference_error",
                "type_validation_error",
                "missing_required_field",
            ]
            for t in error_types
        ), f"Expected compilation error, got: {error_types}"

        # Check error message mentions return, validation, or missing field
        assert any(
            "return" in msg.lower()
            or "validation" in msg.lower()
            or "field" in msg.lower()
            for msg in error_messages
        ), f"Expected error about compilation/validation, got: {error_messages}"

    @pytest.mark.asyncio
    async def test_compose_validates_type_propagation_through_dag(
        self,
        integration_test_session: AsyncSession,
    ):
        """
        Test that compose_workflow propagates types through the DAG.

        Given:
        - Task A outputs {"ip": "string"}
        - Task B expects {"ip": "string"}
        - Task C expects {"domain": "string"} (incompatible)

        When:
        - Composing ["task_a", "task_b", "task_c"]

        Then:
        - Should catch that Task B output doesn't provide "domain" for Task C
        - This requires actual Cy compilation of B with A's output as input

        This test currently FAILS because compose_workflow uses pre-computed
        schemas instead of progressive compilation.
        """
        # Create Task A - outputs IP
        component_a = Component(
            tenant_id="test_tenant",
            cy_name="extract_ip",
            name="Extract IP",
            description="Extracts IP from alert",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_a)
        await integration_test_session.flush()

        task_a = Task(
            component_id=component_a.id,
            script='return {"ip": input["source_ip"]}',
            data_samples=[{"source_ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_a)

        # Create Task B - passes through IP
        component_b = Component(
            tenant_id="test_tenant",
            cy_name="validate_ip",
            name="Validate IP",
            description="Validates IP format",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_b)
        await integration_test_session.flush()

        task_b = Task(
            component_id=component_b.id,
            script='return {"ip": input["ip"]}',  # Outputs same structure
            data_samples=[{"ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_b)

        # Create Task C - expects domain (incompatible!)
        component_c = Component(
            tenant_id="test_tenant",
            cy_name="lookup_domain",
            name="Lookup Domain",
            description="Looks up domain info",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_c)
        await integration_test_session.flush()

        task_c = Task(
            component_id=component_c.id,
            script='return {"whois": input["domain"]}',  # Expects "domain" field!
            data_samples=[{"domain": "example.com"}],
        )
        integration_test_session.add(task_c)
        await integration_test_session.commit()

        # Act
        composer = WorkflowComposerService(session=integration_test_session)
        result = await composer.compose_workflow(
            composition=["extract_ip", "validate_ip", "lookup_domain"],
            workflow_name="IP to Domain Workflow",
            workflow_description="Should fail - IP output doesn't have domain",
            tenant_id="test_tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        # Assert
        assert result.status == "error", (
            "Expected type propagation to catch missing 'domain' field"
        )

        # Check for missing field error
        missing_field_errors = [
            e
            for e in result.errors
            if e.error_type in ["missing_required_field", "type_validation_error"]
            and "domain" in e.message
        ]
        assert len(missing_field_errors) > 0, (
            f"Expected error about missing 'domain' field. Got errors: {result.errors}"
        )

    @pytest.mark.asyncio
    async def test_compose_successful_workflow_with_valid_types(
        self,
        integration_test_session: AsyncSession,
    ):
        """
        Test that compose_workflow succeeds with valid type-compatible tasks.

        Given:
        - Task A outputs {"ip": "string"}
        - Task B expects {"ip": "string"} and outputs {"reputation": "string"}

        When: Composing ["task_a", "task_b"]
        Then: Should succeed with status="success" and workflow_id returned
        """
        # Create Task A - outputs IP
        component_a = Component(
            tenant_id="test_tenant",
            cy_name="extract_ip_valid",
            name="Extract IP Valid",
            description="Extracts IP from alert",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_a)
        await integration_test_session.flush()

        task_a = Task(
            component_id=component_a.id,
            script='return {"ip": input["source_ip"]}',
            data_samples=[{"source_ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_a)

        # Create Task B - accepts IP, outputs reputation
        component_b = Component(
            tenant_id="test_tenant",
            cy_name="check_reputation_valid",
            name="Check Reputation Valid",
            description="Checks IP reputation",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_b)
        await integration_test_session.flush()

        task_b = Task(
            component_id=component_b.id,
            script='return {"reputation": "clean", "ip": input["ip"]}',
            data_samples=[{"ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_b)
        await integration_test_session.commit()

        # Act
        composer = WorkflowComposerService(session=integration_test_session)
        result = await composer.compose_workflow(
            composition=["extract_ip_valid", "check_reputation_valid"],
            workflow_name="IP Reputation Workflow",
            workflow_description="Valid workflow with type-compatible tasks",
            tenant_id="test_tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=True,  # Actually create it
        )

        # Assert
        assert result.status == "success", (
            f"Expected success but got {result.status}. Errors: {result.errors}"
        )
        assert result.workflow_id is not None, "Should return workflow_id on success"
        assert len(result.errors) == 0, f"Should have no errors, got: {result.errors}"

    @pytest.mark.asyncio
    async def test_compose_validates_3task_propagation_chain(
        self,
        integration_test_session: AsyncSession,
    ):
        """
        Test that compose_workflow propagates types through 3-task chain.

        Given:
        - Task A outputs {"ip": "string"}
        - Task B expects {"ip": "string"}, outputs {"ip": "string", "location": "string"}
        - Task C expects {"location": "string"}, outputs {"country": "string"}

        When: Composing ["task_a", "task_b", "task_c"]
        Then: Should validate all 3 edges with proper type propagation
        """
        # Create Task A - outputs IP
        component_a = Component(
            tenant_id="test_tenant",
            cy_name="extract_ip_chain",
            name="Extract IP Chain",
            description="Extracts IP",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_a)
        await integration_test_session.flush()

        task_a = Task(
            component_id=component_a.id,
            script='return {"ip": input["source_ip"]}',
            data_samples=[{"source_ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_a)

        # Create Task B - IP to location
        component_b = Component(
            tenant_id="test_tenant",
            cy_name="ip_to_location_chain",
            name="IP to Location Chain",
            description="Gets location from IP",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_b)
        await integration_test_session.flush()

        task_b = Task(
            component_id=component_b.id,
            script='return {"ip": input["ip"], "location": "US"}',
            data_samples=[{"ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_b)

        # Create Task C - location to country
        component_c = Component(
            tenant_id="test_tenant",
            cy_name="location_to_country_chain",
            name="Location to Country Chain",
            description="Extracts country from location",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_c)
        await integration_test_session.flush()

        task_c = Task(
            component_id=component_c.id,
            script='return {"country": input["location"]}',
            data_samples=[{"location": "US"}],
        )
        integration_test_session.add(task_c)
        await integration_test_session.commit()

        # Act
        composer = WorkflowComposerService(session=integration_test_session)
        result = await composer.compose_workflow(
            composition=[
                "extract_ip_chain",
                "ip_to_location_chain",
                "location_to_country_chain",
            ],
            workflow_name="3-Task Chain Workflow",
            workflow_description="Tests type propagation through 3 tasks",
            tenant_id="test_tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=True,
        )

        # Assert - should succeed
        assert result.status == "success", (
            f"Expected 3-task chain to succeed. Errors: {result.errors}"
        )
        assert result.workflow_id is not None
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_compose_catches_type_mismatch_in_middle_of_chain(
        self,
        integration_test_session: AsyncSession,
    ):
        """
        Test that compose_workflow catches type mismatch in middle of 3-task chain.

        Given:
        - Task A outputs {"ip": "string"}
        - Task B expects {"ip": "string"}, but outputs {"count": number} (WRONG TYPE)
        - Task C expects {"count": "string"} (type mismatch!)

        When: Composing ["task_a", "task_b", "task_c"]
        Then: Should catch the type mismatch between B and C
        """
        # Create Task A
        component_a = Component(
            tenant_id="test_tenant",
            cy_name="task_a_chain_error",
            name="Task A Chain Error",
            description="Outputs IP",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_a)
        await integration_test_session.flush()

        task_a = Task(
            component_id=component_a.id,
            script='return {"ip": input["source_ip"]}',
            data_samples=[{"source_ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_a)

        # Create Task B - outputs NUMBER
        component_b = Component(
            tenant_id="test_tenant",
            cy_name="task_b_chain_error",
            name="Task B Chain Error",
            description="Outputs count as number",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_b)
        await integration_test_session.flush()

        task_b = Task(
            component_id=component_b.id,
            script='return {"count": 42}',  # Number type
            data_samples=[{"ip": "192.168.1.1"}],
        )
        integration_test_session.add(task_b)

        # Create Task C - expects STRING for count field
        component_c = Component(
            tenant_id="test_tenant",
            cy_name="task_c_chain_error",
            name="Task C Chain Error",
            description="Expects count as string",
            kind="task",
            status="enabled",
        )
        integration_test_session.add(component_c)
        await integration_test_session.flush()

        task_c = Task(
            component_id=component_c.id,
            script='return {"result": input["count"] + "_processed"}',  # Expects string
            data_samples=[{"count": "10"}],  # String in data_samples
        )
        integration_test_session.add(task_c)
        await integration_test_session.commit()

        # Act
        composer = WorkflowComposerService(session=integration_test_session)
        result = await composer.compose_workflow(
            composition=[
                "task_a_chain_error",
                "task_b_chain_error",
                "task_c_chain_error",
            ],
            workflow_name="Chain with Type Mismatch",
            workflow_description="Should fail due to type mismatch in middle",
            tenant_id="test_tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        # Assert - should detect type mismatch
        assert result.status == "error", (
            f"Expected to catch type mismatch. Got status={result.status}"
        )
        assert len(result.errors) > 0, "Should have type validation errors"

        # Check error mentions the issue
        error_messages = " ".join([e.message for e in result.errors])
        assert "count" in error_messages.lower() or "type" in error_messages.lower()
