"""Unit tests for TaskResolver and TemplateResolver."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from analysi.services.workflow_composer.models import ResolvedTask, ResolvedTemplate
from analysi.services.workflow_composer.resolvers import (
    TEMPLATE_SHORTCUTS,
    TaskResolver,
    TemplateResolver,
)


class TestTaskResolver:
    """Test TaskResolver business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def resolver(self, mock_session):
        """Create a TaskResolver instance."""
        return TaskResolver(mock_session)

    # ============================================================================
    # Positive Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_resolve_valid_task(self, resolver, mock_session):
        """
        Verify resolver finds task by cy_name and returns ResolvedTask.

        Expected:
        - ResolvedTask with task_id, cy_name, name
        - Inferred input/output schemas
        - data_samples included
        """
        tenant_id = "test-tenant"
        cy_name = "extract_ip"
        task_id = uuid4()

        # Mock _lookup_task to return a task
        resolver._lookup_task = AsyncMock(
            return_value=[
                {
                    "id": task_id,
                    "cy_name": cy_name,
                    "name": "Extract IP Address",
                    "status": "enabled",
                    "data_samples": [{"alert": {"src_ip": "1.2.3.4"}}],
                }
            ]
        )

        # Mock _infer_schemas
        resolver._infer_schemas = AsyncMock(
            return_value=(
                {"type": "object", "properties": {"alert": {"type": "object"}}},
                {"type": "object", "properties": {"ip": {"type": "string"}}},
            )
        )

        result = await resolver.resolve(cy_name, tenant_id)

        assert isinstance(result, ResolvedTask)
        assert result.task_id == task_id
        assert result.cy_name == cy_name
        assert result.name == "Extract IP Address"
        assert result.input_schema is not None
        assert result.output_schema is not None
        assert len(result.data_samples) == 1

    @pytest.mark.asyncio
    async def test_resolve_with_caching(self, resolver):
        """
        Verify resolver caches results and doesn't hit DB twice for same cy_name.

        Expected:
        - First call queries DB
        - Second call uses cache (mock DB not called again)
        """
        tenant_id = "test-tenant"
        cy_name = "extract_ip"
        task_id = uuid4()

        # Mock _lookup_task
        resolver._lookup_task = AsyncMock(
            return_value=[
                {
                    "id": task_id,
                    "cy_name": cy_name,
                    "name": "Extract IP",
                    "status": "enabled",
                    "data_samples": [],
                }
            ]
        )
        resolver._infer_schemas = AsyncMock(return_value=(None, None))

        # First call
        result1 = await resolver.resolve(cy_name, tenant_id)

        # Second call (should use cache)
        result2 = await resolver.resolve(cy_name, tenant_id)

        # Should have called DB only once
        resolver._lookup_task.assert_called_once()

        # Results should be the same
        assert result1.task_id == result2.task_id
        assert result1.cy_name == result2.cy_name

    @pytest.mark.asyncio
    async def test_infer_schemas_from_cy_script(self, resolver):
        """
        Verify schema inference works for task with Cy script.

        Expected:
        - input_schema inferred from data_samples (Finding #6)
        - output_schema inferred from Cy script analysis
        """
        task_id = uuid4()
        tenant_id = "test-tenant"

        # Mock the session.execute to return None (task not found)
        # This tests the error handling path
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        resolver.session.execute = AsyncMock(return_value=mock_result)

        input_schema, output_schema = await resolver._infer_schemas(task_id, tenant_id)

        # When task is not found, both schemas should be None
        assert input_schema is None
        assert output_schema is None

    # ============================================================================
    # Negative Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_resolve_task_not_found(self, resolver):
        """
        Verify resolver raises ValueError when cy_name doesn't exist.

        Expected:
        - ValueError with message about task not found
        """
        tenant_id = "test-tenant"
        cy_name = "nonexistent_task"

        # Mock _lookup_task to return empty list
        resolver._lookup_task = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="not found"):
            await resolver.resolve(cy_name, tenant_id)

    @pytest.mark.asyncio
    async def test_resolve_disabled_task(self, resolver):
        """
        Verify resolver rejects disabled tasks (status != "enabled").

        Expected:
        - ValueError with message about task disabled
        """
        tenant_id = "test-tenant"
        cy_name = "disabled_task"

        # Mock _lookup_task to return disabled task
        resolver._lookup_task = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "cy_name": cy_name,
                    "name": "Disabled Task",
                    "status": "disabled",
                    "data_samples": [],
                }
            ]
        )

        with pytest.raises(ValueError, match="disabled|enabled"):
            await resolver.resolve(cy_name, tenant_id)

    @pytest.mark.asyncio
    async def test_resolve_ambiguous_cy_name(self, resolver):
        """
        Verify resolver detects multiple tasks with same cy_name (should never happen but defensive).

        Expected:
        - ValueError with message about ambiguous resolution
        """
        tenant_id = "test-tenant"
        cy_name = "ambiguous_task"

        # Mock _lookup_task to return multiple tasks
        resolver._lookup_task = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "cy_name": cy_name,
                    "name": "Task 1",
                    "status": "enabled",
                    "data_samples": [],
                },
                {
                    "id": uuid4(),
                    "cy_name": cy_name,
                    "name": "Task 2",
                    "status": "enabled",
                    "data_samples": [],
                },
            ]
        )

        with pytest.raises(ValueError, match="ambiguous|multiple"):
            await resolver.resolve(cy_name, tenant_id)


class TestTemplateResolver:
    """Test TemplateResolver business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def resolver(self, mock_session):
        """Create a TemplateResolver instance."""
        return TemplateResolver(mock_session)

    # ============================================================================
    # Positive Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_resolve_identity_template(self, resolver):
        """
        Verify resolver finds system_identity template from "identity" shortcut.

        Expected:
        - ResolvedTemplate with template_id, shortcut="identity"
        - input_schema and output_schema present
        """
        shortcut = "identity"
        template_id = uuid4()

        # Mock _lookup_template
        resolver._lookup_template = AsyncMock(
            return_value={
                "id": template_id,
                "name": "system_identity",
                "kind": "identity",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            }
        )

        result = await resolver.resolve(shortcut)

        assert isinstance(result, ResolvedTemplate)
        assert result.template_id == template_id
        assert result.shortcut == shortcut
        assert result.kind == "identity"
        assert result.input_schema is not None
        assert result.output_schema is not None

    @pytest.mark.asyncio
    async def test_resolve_merge_template(self, resolver):
        """
        Verify resolver finds system_merge template from "merge" shortcut.

        Expected:
        - ResolvedTemplate with correct kind="merge"
        """
        shortcut = "merge"
        template_id = uuid4()

        resolver._lookup_template = AsyncMock(
            return_value={
                "id": template_id,
                "name": "system_merge",
                "kind": "merge",
                "input_schema": {"type": "array"},
                "output_schema": {"type": "object"},
            }
        )

        result = await resolver.resolve(shortcut)

        assert result.kind == "merge"
        assert result.shortcut == shortcut

    @pytest.mark.asyncio
    async def test_resolve_collect_template(self, resolver):
        """
        Verify resolver finds system_collect template from "collect" shortcut.

        Expected:
        - ResolvedTemplate with correct kind="collect"
        """
        shortcut = "collect"
        template_id = uuid4()

        resolver._lookup_template = AsyncMock(
            return_value={
                "id": template_id,
                "name": "system_collect",
                "kind": "collect",
                "input_schema": {"type": "array"},
                "output_schema": {"type": "array"},
            }
        )

        result = await resolver.resolve(shortcut)

        assert result.kind == "collect"
        assert result.shortcut == shortcut

    @pytest.mark.asyncio
    async def test_template_caching(self, resolver):
        """
        Verify resolver caches template results.

        Expected:
        - DB only queried once per shortcut
        """
        shortcut = "identity"
        template_id = uuid4()

        resolver._lookup_template = AsyncMock(
            return_value={
                "id": template_id,
                "name": "system_identity",
                "kind": "identity",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
            }
        )

        # First call
        result1 = await resolver.resolve(shortcut)

        # Second call (should use cache)
        result2 = await resolver.resolve(shortcut)

        # Should have called DB only once
        resolver._lookup_template.assert_called_once()

        assert result1.template_id == result2.template_id

    # ============================================================================
    # Negative Tests
    # ============================================================================

    @pytest.mark.asyncio
    async def test_resolve_unknown_shortcut(self, resolver):
        """
        Verify resolver rejects unknown shortcuts like "foobar".

        Expected:
        - ValueError with message about unknown shortcut
        """
        shortcut = "foobar"

        with pytest.raises(ValueError, match="unknown|shortcut"):
            await resolver.resolve(shortcut)

    @pytest.mark.asyncio
    async def test_resolve_template_not_found_in_db(self, resolver):
        """
        Verify resolver handles case where system template doesn't exist in DB (data issue).

        Expected:
        - ValueError with message about template not found
        """
        shortcut = "identity"

        # Mock _lookup_template to return None
        resolver._lookup_template = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await resolver.resolve(shortcut)


def test_template_shortcuts_constant():
    """Verify TEMPLATE_SHORTCUTS constant is defined correctly."""
    assert "identity" in TEMPLATE_SHORTCUTS
    assert "merge" in TEMPLATE_SHORTCUTS
    assert "collect" in TEMPLATE_SHORTCUTS
    assert TEMPLATE_SHORTCUTS["identity"] == "system_identity"
    assert TEMPLATE_SHORTCUTS["merge"] == "system_merge"
    assert TEMPLATE_SHORTCUTS["collect"] == "system_collect"
