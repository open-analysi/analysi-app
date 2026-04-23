"""Unit tests for WorkflowService business logic."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.workflow import Workflow
from analysi.repositories.workflow import NodeTemplateRepository, WorkflowRepository
from analysi.schemas.workflow import (
    WorkflowCreate,
    WorkflowNodeCreate,
)
from analysi.services.workflow import NodeTemplateService, WorkflowService


@pytest.mark.unit
class TestWorkflowService:
    """Test WorkflowService business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_workflow_repo(self, mock_session):
        """Create a mock WorkflowRepository."""
        mock_repo = AsyncMock(spec=WorkflowRepository)
        mock_repo.session = mock_session  # Add session attribute for type propagation
        return mock_repo

    @pytest.fixture
    def mock_template_repo(self):
        """Create a mock NodeTemplateRepository."""
        return AsyncMock(spec=NodeTemplateRepository)

    @pytest.fixture
    def service(self, mock_session, mock_workflow_repo, mock_template_repo):
        """Create a WorkflowService instance with mocks."""
        service = WorkflowService(mock_session)
        service.workflow_repo = mock_workflow_repo
        service.template_repo = mock_template_repo
        return service

    @pytest.mark.asyncio
    async def test_create_workflow_calls_implementation(self, service):
        """Test that create_workflow calls the implementation with mocked repo."""
        from datetime import UTC, datetime
        from uuid import uuid4

        tenant_id = "test-tenant"
        template_id = uuid4()

        # Mock template validation to pass
        mock_template = MagicMock()
        mock_template.enabled = True
        service.template_repo.get_template_by_id.return_value = mock_template

        # Create minimal Rodos-compliant workflow data
        workflow_data = WorkflowCreate(
            name="Test Workflow",
            io_schema={
                "input": {
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                    "required": ["data"],
                },
                "output": {"type": "object"},
            },
            created_by=str(SYSTEM_USER_ID),
            data_samples=[{"data": "test_value"}],
            nodes=[
                WorkflowNodeCreate(
                    node_id="n1",
                    kind="transformation",
                    name="Start Node",
                    is_start_node=True,
                    node_template_id=template_id,
                    schemas={"input": {"type": "object"}, "output": {"type": "object"}},
                )
            ],
            edges=[],
        )

        # Mock workflow creation result with proper attributes
        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.id = uuid4()
        mock_workflow.tenant_id = tenant_id
        mock_workflow.name = "Test Workflow"
        mock_workflow.description = None
        mock_workflow.is_dynamic = False
        mock_workflow.io_schema = {
            "input": {
                "type": "object",
                "properties": {"data": {"type": "string"}},
                "required": ["data"],
            },
            "output": {"type": "object"},
        }
        mock_workflow.data_samples = [{"data": "test_value"}]
        mock_workflow.status = "draft"
        mock_workflow.created_by = SYSTEM_USER_ID
        mock_workflow.planner_id = None
        mock_workflow.created_at = datetime.now(tz=UTC)
        mock_workflow.nodes = []
        mock_workflow.edges = []

        service.workflow_repo.create_workflow.return_value = mock_workflow

        # Test the service call
        result = await service.create_workflow(tenant_id, workflow_data)

        # Verify the service was called and returned a WorkflowResponse
        service.workflow_repo.create_workflow.assert_called_once()
        assert result is not None
        assert hasattr(result, "name")
        assert result.name == "Test Workflow"

    @pytest.mark.asyncio
    async def test_get_workflow_calls_stubbed_method(self, service):
        """Test that get_workflow calls the implementation and handles None result."""

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()

        # Mock repository to return None (workflow not found)
        service.workflow_repo.get_workflow_by_id.return_value = None

        result = await service.get_workflow(tenant_id, workflow_id)

        # Verify repository was called
        service.workflow_repo.get_workflow_by_id.assert_called_once_with(
            tenant_id, workflow_id
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_list_workflows_calls_stubbed_method(self, service):
        """Test that list_workflows calls the implementation and returns paginated response."""
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        service.workflow_repo.list_workflows.return_value = ([], 0)

        result = await service.list_workflows(tenant_id, skip=0, limit=10)

        # Verify repository was called
        service.workflow_repo.list_workflows.assert_called_once_with(
            tenant_id=tenant_id, skip=0, limit=10, name_filter=None, app=None
        )
        # Service now returns tuple (workflows, metadata) per established pattern
        workflows, metadata = result
        assert workflows is not None
        assert metadata is not None
        assert metadata["total"] == 0
        assert len(workflows) == 0

    # UPDATE: Removed test_update_workflow_calls_stubbed_method since workflows are now immutable
    # Workflows cannot be updated once created per v3 spec

    @pytest.mark.asyncio
    async def test_delete_workflow_calls_stubbed_method(self, service):
        """Test that delete_workflow calls the implementation and returns boolean."""
        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()

        # Mock repository to return False (workflow not found)
        service.workflow_repo.delete_workflow.return_value = False

        result = await service.delete_workflow(tenant_id, workflow_id)

        # Verify repository was called
        service.workflow_repo.delete_workflow.assert_called_once_with(
            tenant_id, workflow_id
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_workflow_definition_calls_stubbed_method(self, service):
        """Test that validate_workflow_definition validates Rodos-compliant workflows."""
        template_id = uuid.uuid4()
        workflow_data = WorkflowCreate(
            name="Test Workflow",
            io_schema={
                "input": {
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                    "required": ["data"],
                },
                "output": {"type": "object"},
            },
            created_by=str(SYSTEM_USER_ID),
            data_samples=[{"data": "test_value"}],
            nodes=[
                WorkflowNodeCreate(
                    node_id="n1",
                    kind="transformation",
                    name="Test Node",
                    is_start_node=True,
                    node_template_id=template_id,
                    schemas={"input": {"type": "object"}, "output": {"type": "object"}},
                )
            ],
            edges=[],
        )

        # Mock template validation to pass
        mock_template = MagicMock()
        mock_template.enabled = True
        service.template_repo.get_template_by_id.return_value = mock_template

        result = await service.validate_workflow_definition(workflow_data)

        # Verify validation response structure
        assert isinstance(result, dict)
        assert "valid" in result
        assert result["valid"] is True
        assert "node_count" in result
        assert result["node_count"] == 1


@pytest.mark.unit
class TestNodeTemplateService:
    """Test NodeTemplateService business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_template_repo(self):
        """Create a mock NodeTemplateRepository."""
        return AsyncMock(spec=NodeTemplateRepository)

    @pytest.fixture
    def service(self, mock_session, mock_template_repo):
        """Create a NodeTemplateService instance with mocks."""
        service = NodeTemplateService(mock_session)
        service.template_repo = mock_template_repo
        return service

    @pytest.mark.asyncio
    async def test_create_template_calls_stubbed_method(self, service):
        """Test that create_template calls the implementation and returns template response."""
        from datetime import UTC, datetime

        from analysi.models.workflow import NodeTemplate
        from analysi.schemas.workflow import NodeTemplateCreate

        tenant_id = "test-tenant"
        template_data = NodeTemplateCreate(
            name="test_template",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            code="return inp",
        )

        # Mock repository to return created template
        mock_template = MagicMock(spec=NodeTemplate)
        mock_template.id = uuid.uuid4()
        mock_template.resource_id = uuid.uuid4()
        mock_template.tenant_id = tenant_id
        mock_template.name = "test_template"
        mock_template.description = None
        mock_template.input_schema = {"type": "object"}
        mock_template.output_schema = {"type": "object"}
        mock_template.code = "return inp"
        mock_template.language = "python"
        mock_template.type = "transformation"
        mock_template.kind = "identity"  # Type inference classification
        mock_template.enabled = True
        mock_template.revision_num = 1
        mock_template.created_at = datetime.now(tz=UTC)

        service.template_repo.create_template.return_value = mock_template

        result = await service.create_template(template_data, tenant_id)

        # Verify repository was called and response structure
        service.template_repo.create_template.assert_called_once_with(
            template_data, tenant_id
        )
        assert result is not None
        assert hasattr(result, "name")
        assert result.name == "test_template"

    @pytest.mark.asyncio
    async def test_get_template_calls_stubbed_method(self, service):
        """Test that get_template calls the implementation and handles not found."""
        template_id = uuid.uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return None (template not found)
        service.template_repo.get_template_by_id.return_value = None

        result = await service.get_template(template_id, tenant_id)

        # Verify repository was called with tenant scoping
        service.template_repo.get_template_by_id.assert_called_once_with(
            template_id, tenant_id
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_list_templates_calls_stubbed_method(self, service):
        """Test that list_templates calls the implementation and returns paginated response."""
        tenant_id = "test-tenant"

        # Mock repository to return empty list
        service.template_repo.list_templates.return_value = ([], 0)

        result = await service.list_templates(tenant_id, skip=0, limit=10)

        # Verify repository was called
        service.template_repo.list_templates.assert_called_once_with(
            tenant_id=tenant_id, skip=0, limit=10, enabled_only=False, name_filter=None
        )
        # Service now returns tuple (templates, metadata) per established pattern
        templates, metadata = result
        assert templates is not None
        assert metadata is not None
        assert metadata["total"] == 0
        assert len(templates) == 0

    # UPDATE: Removed test_update_template_calls_stubbed_method since node templates are now immutable
    # Node templates cannot be updated once created to preserve workflow reproducibility

    @pytest.mark.asyncio
    async def test_delete_template_calls_stubbed_method(self, service):
        """Test that delete_template calls the implementation and returns boolean."""
        template_id = uuid.uuid4()
        tenant_id = "test-tenant"

        # Mock repository to return False (template not found)
        service.template_repo.delete_template.return_value = False

        result = await service.delete_template(template_id, tenant_id)

        # Verify repository was called with tenant scoping
        service.template_repo.delete_template.assert_called_once_with(
            template_id, tenant_id
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_template_code_calls_stubbed_method(self, service):
        """Test that validate_template_code calls the implementation and returns validation result."""
        code = "return inp.get('field')"

        result = await service.validate_template_code(code)

        # Verify validation response structure
        assert isinstance(result, dict)
        assert "valid" in result
        assert result["valid"] is True
        assert "language" in result
        assert result["language"] == "python"


@pytest.mark.unit
class TestWorkflowServiceHelperFunctions:
    """Test helper functions in workflow service module."""

    def test_validate_dag_structure_calls_implementation(self):
        """Test that validate_dag_structure calls the implementation."""
        nodes = [{"node_id": "a"}, {"node_id": "b"}]
        edges = [{"from_node_id": "a", "to_node_id": "b"}]

        # This should pass now that we have real implementation
        from analysi.services.workflow import validate_dag_structure

        result = validate_dag_structure(nodes, edges)
        assert isinstance(result, dict)
        assert result["valid"] is True

    def test_enrich_workflow_response_enriches_workflow(self):
        """Test that enrich_workflow_response enriches workflow with template code and task details."""
        workflow_id = str(uuid.uuid4())
        template_id = uuid.uuid4()
        task_id = uuid.uuid4()

        workflow = {
            "id": workflow_id,
            "name": "Test",
            "nodes": [{"node_template_id": template_id, "task_id": task_id}],
        }
        template_code = {template_id: "def transform(data): return data"}
        task_details = {task_id: {"name": "Test Task", "function": "reasoning"}}

        from analysi.services.workflow import enrich_workflow_response

        result = enrich_workflow_response(workflow, template_code, task_details)

        assert isinstance(result, dict)
        assert result["id"] == workflow_id
        assert "nodes" in result
        assert "template_code" in result["nodes"][0]
        assert "task_details" in result["nodes"][0]

    def test_validate_node_schemas_validates_correctly(self):
        """Test that validate_node_schemas validates node schemas correctly."""
        nodes = [
            {
                "kind": "task",
                "schemas": {"input": {"type": "object"}, "output": {"type": "object"}},
            }
        ]

        from analysi.services.workflow import validate_node_schemas

        result = validate_node_schemas(nodes)
        assert result is True

    def test_validate_node_schemas_invalid_kind(self):
        """Test that validate_node_schemas raises error for invalid node kind."""
        nodes = [{"schemas": {"input": {"type": "object"}}}]  # Missing kind

        from analysi.services.workflow import validate_node_schemas

        with pytest.raises(ValueError, match="Node 0 has invalid kind: None"):
            validate_node_schemas(nodes)


@pytest.mark.unit
class TestWorkflowServiceTypeValidation:
    """Test WorkflowService type validation methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_workflow_repo(self, mock_session):
        """Create a mock WorkflowRepository."""
        mock_repo = AsyncMock(spec=WorkflowRepository)
        mock_repo.session = mock_session  # Add session attribute for type propagation
        return mock_repo

    @pytest.fixture
    def mock_template_repo(self):
        """Create a mock NodeTemplateRepository."""
        return AsyncMock(spec=NodeTemplateRepository)

    @pytest.fixture
    def service(self, mock_session, mock_workflow_repo, mock_template_repo):
        """Create a WorkflowService instance with mocks."""
        service = WorkflowService(mock_session)
        service.workflow_repo = mock_workflow_repo
        service.template_repo = mock_template_repo
        return service

    @pytest.mark.asyncio
    async def test_validate_workflow_types_with_valid_workflow(self, service):
        """Test that validate_workflow_types calls WorkflowTypePropagator and converts result."""
        # Given: Mocked workflow with nodes/edges
        from unittest.mock import MagicMock, patch

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}

        # Mock workflow with node and template
        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.id = workflow_id
        mock_workflow.nodes = []
        mock_workflow.edges = []

        service.workflow_repo.get_workflow_by_id.return_value = mock_workflow

        # Mock the type propagator
        with patch(
            "analysi.services.type_propagation.WorkflowTypePropagator"
        ) as MockPropagator:
            mock_propagator_instance = MockPropagator.return_value
            # propagate_types is async, so return an AsyncMock
            mock_propagator_instance.propagate_types = AsyncMock(
                return_value=MagicMock(
                    status="valid",
                    nodes=[],
                    workflow_output_schema={"type": "object"},
                    errors=[],
                    warnings=[],
                )
            )

            # When: Call validate_workflow_types
            result = await service.validate_workflow_types(
                tenant_id, workflow_id, input_schema
            )

            # Then: Verify result structure
            assert result["status"] == "valid"
            assert "nodes" in result
            assert "workflow_output_schema" in result
            assert "errors" in result
            assert "warnings" in result

    @pytest.mark.asyncio
    async def test_validate_workflow_types_with_invalid_workflow(self, service):
        """Test that validation returns errors for type-unsafe workflows."""
        # Given: Mocked workflow with type errors
        from unittest.mock import MagicMock, patch

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        input_schema = {"type": "object"}

        # Mock workflow
        mock_workflow = MagicMock(spec=Workflow)
        service.workflow_repo.get_workflow_by_id.return_value = mock_workflow

        # Mock propagator to return invalid status with errors
        with patch(
            "analysi.services.type_propagation.WorkflowTypePropagator"
        ) as MockPropagator:
            mock_error = MagicMock(
                node_id="n1",
                error_type="TypeMismatchError",
                message="Type mismatch",
                suggestion="Fix types",
            )
            mock_propagator_instance = MockPropagator.return_value
            mock_propagator_instance.propagate_types = AsyncMock(
                return_value=MagicMock(
                    status="invalid",
                    nodes=[],
                    workflow_output_schema=None,
                    errors=[mock_error],
                    warnings=[],
                )
            )

            # When: Call validate_workflow_types
            result = await service.validate_workflow_types(
                tenant_id, workflow_id, input_schema
            )

            # Then: Verify invalid status and errors
            assert result["status"] == "invalid"
            assert len(result["errors"]) == 1
            assert result["errors"][0]["error_type"] == "TypeMismatchError"

    @pytest.mark.asyncio
    async def test_validate_workflow_types_workflow_not_found(self, service):
        """Test that ValueError raised when workflow doesn't exist."""
        # Given: Mocked repository returning None (workflow not found)
        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        input_schema = {"type": "object"}

        # Mock repository to return None
        service.workflow_repo.get_workflow_by_id.return_value = None

        # When/Then: Should raise ValueError
        with pytest.raises(ValueError, match="not found"):
            await service.validate_workflow_types(tenant_id, workflow_id, input_schema)

    @pytest.mark.asyncio
    async def test_apply_workflow_types_persists_valid_workflow(self, service):
        """Test that apply_workflow_types persists type annotations to database."""
        # Given: Mocked workflow with valid type propagation result
        from unittest.mock import MagicMock, patch

        from analysi.models.workflow import WorkflowNode

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}

        # Mock workflow with nodes
        mock_node = MagicMock(spec=WorkflowNode)
        mock_node.node_id = "n1"
        mock_node.schemas = {"input": {"type": "object"}, "output": {"type": "object"}}

        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.id = workflow_id
        mock_workflow.nodes = [mock_node]
        mock_workflow.io_schema = {
            "input": {"type": "object"},
            "output": {"type": "object"},
        }

        service.workflow_repo.get_workflow_by_id.return_value = mock_workflow

        # Mock propagator to return valid result
        with patch(
            "analysi.services.type_propagation.WorkflowTypePropagator"
        ) as MockPropagator:
            mock_node_info = MagicMock(
                node_id="n1",
                kind="transformation",
                template_kind="static",
                inferred_input={
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                inferred_output={
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
            )
            mock_propagator_instance = MockPropagator.return_value
            mock_propagator_instance.propagate_types = AsyncMock(
                return_value=MagicMock(
                    status="valid",
                    nodes=[mock_node_info],
                    workflow_output_schema={
                        "type": "object",
                        "properties": {"result": {"type": "string"}},
                    },
                    errors=[],
                    warnings=[],
                )
            )

            # When: Call apply_workflow_types
            result = await service.apply_workflow_types(
                tenant_id, workflow_id, input_schema
            )

            # Then: Verify result includes applied metadata
            assert result["status"] == "valid"
            assert result["applied"] is True
            assert result["nodes_updated"] == 1
            assert "updated_at" in result
            service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_workflow_types_rejects_invalid_workflow(self, service):
        """Test that apply does NOT persist if validation fails."""
        # Given: Mocked workflow with status="invalid" from propagator
        from unittest.mock import MagicMock, patch

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        input_schema = {"type": "object"}

        # Mock workflow
        mock_workflow = MagicMock(spec=Workflow)
        service.workflow_repo.get_workflow_by_id.return_value = mock_workflow

        # Mock propagator to return invalid status
        with patch(
            "analysi.services.type_propagation.WorkflowTypePropagator"
        ) as MockPropagator:
            mock_propagator_instance = MockPropagator.return_value
            mock_propagator_instance.propagate_types = AsyncMock(
                return_value=MagicMock(
                    status="invalid",
                    nodes=[],
                    workflow_output_schema=None,
                    errors=[
                        MagicMock(
                            node_id="n1",
                            error_type="Error",
                            message="Error",
                            suggestion="Fix",
                        )
                    ],
                    warnings=[],
                )
            )

            # When/Then: Should raise ValueError for invalid workflow
            with pytest.raises(ValueError, match="Cannot apply types"):
                await service.apply_workflow_types(tenant_id, workflow_id, input_schema)

    @pytest.mark.asyncio
    async def test_apply_workflow_types_allows_warnings(self, service):
        """Test that apply persists workflows with status='valid_with_warnings'."""
        # Given: Mocked workflow with status="valid_with_warnings" (v5 backward compatibility)
        from unittest.mock import MagicMock, patch

        from analysi.models.workflow import WorkflowNode

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()
        input_schema = {"type": "object"}

        # Mock workflow with nodes
        mock_node = MagicMock(spec=WorkflowNode)
        mock_node.node_id = "n1"
        mock_node.schemas = {"input": {"type": "object"}, "output": {"type": "object"}}

        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.nodes = [mock_node]
        mock_workflow.io_schema = {
            "input": {"type": "object"},
            "output": {"type": "object"},
        }

        service.workflow_repo.get_workflow_by_id.return_value = mock_workflow

        # Mock propagator to return valid_with_warnings
        with patch(
            "analysi.services.type_propagation.WorkflowTypePropagator"
        ) as MockPropagator:
            mock_node_info = MagicMock(
                node_id="n1",
                kind="task",
                template_kind=None,
                inferred_input={"type": "object"},
                inferred_output={"type": "object"},
            )
            mock_warning = MagicMock(
                node_id="n1",
                error_type="DeprecatedMultiInputWarning",
                message="Multi-input deprecated",
                suggestion="Add Merge node",
            )
            mock_propagator_instance = MockPropagator.return_value
            mock_propagator_instance.propagate_types = AsyncMock(
                return_value=MagicMock(
                    status="valid_with_warnings",
                    nodes=[mock_node_info],
                    workflow_output_schema={"type": "object"},
                    errors=[],
                    warnings=[mock_warning],
                )
            )

            # When: Call apply_workflow_types
            result = await service.apply_workflow_types(
                tenant_id, workflow_id, input_schema
            )

            # Then: Verify it persists despite warnings
            assert result["status"] == "valid_with_warnings"
            assert result["applied"] is True
            assert len(result["warnings"]) == 1
            service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_workflow_types_removes_annotations(self, service):
        """Test that clear_workflow_types removes all inferred type fields."""
        # Given: Workflow with type annotations in WorkflowNode.schemas
        from unittest.mock import MagicMock

        from analysi.models.workflow import WorkflowNode

        tenant_id = "test-tenant"
        workflow_id = uuid.uuid4()

        # Mock workflow with annotated nodes
        mock_node = MagicMock(spec=WorkflowNode)
        mock_node.schemas = {
            "input": {"type": "object"},
            "output": {"type": "object"},
            "inferred_input": {
                "type": "object",
                "properties": {"ip": {"type": "string"}},
            },
            "inferred_output": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
            "type_checked": True,
            "validated_at": "2024-01-01T00:00:00Z",
        }

        mock_workflow = MagicMock(spec=Workflow)
        mock_workflow.id = workflow_id
        mock_workflow.nodes = [mock_node]

        service.workflow_repo.get_workflow_by_id.return_value = mock_workflow

        # When: Call clear_workflow_types
        result = await service.clear_workflow_types(tenant_id, workflow_id)

        # Then: Verify annotations removed
        assert result["success"] is True
        assert result["nodes_updated"] == 1
        assert result["workflow_id"] == str(workflow_id)
        service.session.commit.assert_called_once()
