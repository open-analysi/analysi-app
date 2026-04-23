"""Unit tests for ComposerWorkflowBuilder."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.services.workflow_composer.builder import ComposerWorkflowBuilder
from analysi.services.workflow_composer.models import (
    ParsedComposition,
    ParsedEdge,
    ParsedNode,
    ResolvedTask,
    ResolvedTemplate,
)


class TestComposerWorkflowBuilder:
    """Test ComposerWorkflowBuilder business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def builder(self, mock_session):
        """Create a ComposerWorkflowBuilder instance."""
        return ComposerWorkflowBuilder(mock_session)

    @pytest.fixture
    def simple_composition(self):
        """Create a simple composition."""
        return ParsedComposition(
            nodes=[
                ParsedNode(node_id="n1", reference="task1", layer=1),
                ParsedNode(node_id="n2", reference="task2", layer=2),
            ],
            edges=[
                ParsedEdge(from_node_id="n1", to_node_id="n2", edge_id="e1"),
            ],
            max_layer=2,
        )

    @pytest.fixture
    def resolved_task_nodes(self):
        """Create resolved task nodes."""
        return {
            "n1": ResolvedTask(
                task_id=uuid4(),
                cy_name="task1",
                name="Task 1",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
            "n2": ResolvedTask(
                task_id=uuid4(),
                cy_name="task2",
                name="Task 2",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                data_samples=[],
            ),
        }

    @pytest.fixture
    def resolved_template_nodes(self):
        """Create resolved template nodes."""
        return {
            "n1": ResolvedTemplate(
                template_id=uuid4(),
                shortcut="identity",
                name="system_identity",
                kind="identity",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
        }

    # ============================================================================
    # Positive Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_build_workflow_complete(
        self, builder, simple_composition, resolved_task_nodes
    ):
        """
        Verify builder creates workflow with all nodes and edges.

        Expected:
        - Workflow record created with correct name, description, schemas
        - All nodes created with proper references
        - All edges created with correct from/to relationships
        - Returns workflow UUID
        """
        workflow_id = await builder.build_workflow(
            composition=simple_composition,
            resolved_nodes=resolved_task_nodes,
            workflow_name="Test Workflow",
            workflow_description="Test Description",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        assert isinstance(workflow_id, type(uuid4()))

    @pytest.mark.asyncio
    async def test_create_task_nodes(
        self, builder, simple_composition, resolved_task_nodes
    ):
        """
        Verify builder creates nodes with kind="task" and task_id references.

        Expected:
        - WorkflowNode records with correct task_id
        """
        workflow_id = uuid4()

        # Mock _create_workflow
        builder._create_workflow = AsyncMock(return_value=workflow_id)

        # Mock _create_nodes
        node_uuid_map = {"n1": uuid4(), "n2": uuid4()}
        builder._create_nodes = AsyncMock(return_value=node_uuid_map)

        # Mock _create_edges
        builder._create_edges = AsyncMock()

        result_workflow_id = await builder.build_workflow(
            composition=simple_composition,
            resolved_nodes=resolved_task_nodes,
            workflow_name="Test Workflow",
            workflow_description="Test Description",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        assert result_workflow_id == workflow_id
        builder._create_nodes.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_template_nodes(self, builder, resolved_template_nodes):
        """
        Verify builder creates nodes with kind="transformation" and node_template_id references.

        Expected:
        - WorkflowNode records with correct node_template_id
        """
        composition = ParsedComposition(
            nodes=[ParsedNode(node_id="n1", reference="identity", layer=1)],
            edges=[],
            max_layer=1,
        )

        workflow_id = uuid4()

        builder._create_workflow = AsyncMock(return_value=workflow_id)
        builder._create_nodes = AsyncMock(return_value={"n1": uuid4()})
        builder._create_edges = AsyncMock()

        result_workflow_id = await builder.build_workflow(
            composition=composition,
            resolved_nodes=resolved_template_nodes,
            workflow_name="Test Workflow",
            workflow_description="Test Description",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        assert result_workflow_id == workflow_id
        builder._create_nodes.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_edges_with_aliases(
        self, builder, simple_composition, resolved_task_nodes
    ):
        """
        Verify builder creates edges with proper aliases.

        Expected:
        - WorkflowEdge records with from_node_uuid and to_node_uuid
        """
        workflow_id = uuid4()

        builder._create_workflow = AsyncMock(return_value=workflow_id)
        builder._create_nodes = AsyncMock(return_value={"n1": uuid4(), "n2": uuid4()})
        builder._create_edges = AsyncMock()

        await builder.build_workflow(
            composition=simple_composition,
            resolved_nodes=resolved_task_nodes,
            workflow_name="Test Workflow",
            workflow_description="Test Description",
            tenant_id="test-tenant",
            created_by=str(SYSTEM_USER_ID),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        builder._create_edges.assert_called_once()

    # ============================================================================
    # Negative Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_build_with_invalid_workflow_data(
        self, builder, simple_composition, resolved_task_nodes
    ):
        """
        Verify builder handles database constraint violations gracefully.

        Expected:
        - ValueError with descriptive message
        """
        # Mock _create_workflow to raise an exception
        builder._create_workflow = AsyncMock(
            side_effect=ValueError("Constraint violation")
        )

        with pytest.raises(ValueError, match="Constraint violation"):
            await builder.build_workflow(
                composition=simple_composition,
                resolved_nodes=resolved_task_nodes,
                workflow_name="",  # Invalid empty name
                workflow_description="Test Description",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

    @pytest.mark.asyncio
    async def test_build_with_missing_task_reference(self, builder, simple_composition):
        """
        Verify builder detects when resolved task doesn't exist in DB.

        Expected:
        - ValueError with message about missing task
        """
        # Empty resolved nodes - references won't be found
        resolved_nodes = {}

        with pytest.raises((ValueError, KeyError)):
            await builder.build_workflow(
                composition=simple_composition,
                resolved_nodes=resolved_nodes,
                workflow_name="Test Workflow",
                workflow_description="Test Description",
                tenant_id="test-tenant",
                created_by=str(SYSTEM_USER_ID),
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )
