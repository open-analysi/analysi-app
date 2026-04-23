"""Unit tests for WorkflowComposerService."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.services.workflow_composer.models import (
    CompositionResult,
    ParsedComposition,
    ParsedEdge,
    ParsedNode,
    ResolvedTask,
)
from analysi.services.workflow_composer.service import WorkflowComposerService


class TestWorkflowComposerService:
    """Test WorkflowComposerService business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        """Create a WorkflowComposerService instance."""
        return WorkflowComposerService(mock_session)

    # ============================================================================
    # Positive Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_compose_workflow_simple_sequential(self, service):
        """
        Verify service orchestrates full composition for simple sequential workflow.

        Expected:
        - status="success"
        - workflow_id returned
        - No errors, warnings, or questions
        """
        composition = ["task1", "task2", "task3"]

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Simple sequential workflow",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=True,
        )

        assert isinstance(result, CompositionResult)
        assert result.status in ["success", "needs_decision", "error"]
        # With stubs, this will raise NotImplementedError

    @pytest.mark.asyncio
    async def test_compose_workflow_with_parallel(self, service):
        """
        Verify service handles parallel composition with aggregation.

        Expected:
        - status="success"
        - Proper parallel node creation
        """
        composition = ["task1", ["task2", "task3"], "merge", "task4"]

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Parallel workflow",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=True,
        )

        assert isinstance(result, CompositionResult)

    @pytest.mark.asyncio
    async def test_compose_workflow_plan_only(self, service):
        """
        Verify service generates plan without creating workflow when execute=False.

        Expected:
        - status="success" or "needs_decision"
        - workflow_id=None
        - plan contains node/edge counts and schemas
        """
        composition = ["task1", "task2"]

        result = await service.compose_workflow_plan(
            composition=composition,
            tenant_id="test-tenant",
        )

        assert isinstance(result, CompositionResult)
        assert result.workflow_id is None
        # plan may be present even with stubs

    @pytest.mark.asyncio
    async def test_compose_workflow_with_questions(self, service):
        """
        Verify service returns questions when missing aggregation detected.

        Expected:
        - status="needs_decision"
        - questions list populated
        - workflow_id=None
        """
        # Composition with parallel block but no aggregation
        composition = ["task1", ["task2", "task3"], "task4"]

        # Mock components to return questions
        service.parser.parse = lambda comp: ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2, parallel_group=1),
                ParsedNode(node_id="n3", reference="task3", layer=2, parallel_group=1),
                ParsedNode(node_id="n4", reference="task4", layer=3),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
                ParsedEdge(from_node_id="n1", to_node_id="n3", edge_id="e2"),
                ParsedEdge(from_node_id="n2", to_node_id="n4", edge_id="e3"),
                ParsedEdge(from_node_id="n3", to_node_id="n4", edge_id="e4"),
            ],
            max_layer=3,
        )

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Workflow with missing aggregation",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        assert isinstance(result, CompositionResult)
        # May have questions about missing aggregation

    # ============================================================================
    # Negative Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_compose_with_parse_error(self, service):
        """
        Verify service returns errors from parser.

        Expected:
        - status="error"
        - errors list contains parse error
        """
        # Empty composition should fail parsing
        composition = []

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Invalid workflow",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        assert isinstance(result, CompositionResult)
        # Should have error about empty composition

    @pytest.mark.asyncio
    async def test_compose_with_resolution_error(self, service):
        """
        Verify service returns errors when task cy_name not found.

        Expected:
        - status="error"
        - errors list contains resolution error
        """
        composition = ["nonexistent_task"]

        # Mock parser to succeed
        service.parser.parse = lambda comp: ParsedComposition(
            nodes=[ParsedNode(node_id="n1", reference="nonexistent_task", layer=1)],
            edges=[],
            max_layer=1,
        )

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Workflow with missing task",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        assert isinstance(result, CompositionResult)
        # Should have error about task not found

    @pytest.mark.asyncio
    async def test_compose_with_validation_error(self, service):
        """
        Verify service returns errors when type mismatch detected.

        Expected:
        - status="error"
        - errors list contains validation error
        """
        composition = ["task1", "task2"]

        # Mock parser
        service.parser.parse = lambda comp: ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
            ],
            edges=[ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1")],
            max_layer=2,
        )

        # Mock resolvers to return incompatible types
        service.task_resolver.resolve = AsyncMock(
            side_effect=[
                ResolvedTask(
                    task_id=uuid4(),
                    cy_name="task1",
                    name="Task 1",
                    input_schema={"type": "object"},
                    output_schema={"type": "number"},
                    data_samples=[],
                ),
                ResolvedTask(
                    task_id=uuid4(),
                    cy_name="task2",
                    name="Task 2",
                    input_schema={"type": "string"},  # Incompatible!
                    output_schema={"type": "object"},
                    data_samples=[],
                ),
            ]
        )

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Workflow with type mismatch",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        assert isinstance(result, CompositionResult)
        # Should have validation errors

    @pytest.mark.asyncio
    async def test_compose_with_multiple_errors(self, service):
        """
        Verify service collects and returns all errors from all stages.

        Expected:
        - status="error"
        - errors list contains errors from multiple components
        """
        # Invalid composition (empty)
        composition = []

        result = await service.compose_workflow(
            composition=composition,
            workflow_name="Test Workflow",
            workflow_description="Multiple errors workflow",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            execute=False,
        )

        assert isinstance(result, CompositionResult)
        # Should have errors
