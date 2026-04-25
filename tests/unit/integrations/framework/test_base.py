"""
Unit tests for IntegrationAction base class.

Tests UT-01.1 through UT-01.4 from TEST_PLAN.md
"""

import pytest

from analysi.integrations.framework.base import IntegrationAction


class TestIntegrationActionBase:
    """Test IntegrationAction base class initialization and metadata."""

    def test_ut_01_1_subclass_initialization(self):
        """UT-01.1: Create IntegrationAction subclass, verify all fields initialized correctly."""

        class TestAction(IntegrationAction):
            async def execute(self, **kwargs):
                return {"status": "success"}

        action = TestAction(
            integration_id="test-integration",
            action_id="test-action",
            settings={"host": "example.com", "port": 443},
            credentials={"api_key": "secret123"},
        )

        assert action.integration_id == "test-integration"
        assert action.action_id == "test-action"
        assert action.settings == {"host": "example.com", "port": 443}
        assert action.credentials == {"api_key": "secret123"}
        assert action._action_type is None  # Not set yet

    def test_ut_01_2_action_type_metadata(self):
        """UT-01.2: Set action_type, verify properties return correct values."""

        class TestAction(IntegrationAction):
            async def execute(self, **kwargs):
                return {"status": "success"}

        action = TestAction(
            integration_id="test-integration",
            action_id="test-action",
            settings={},
            credentials={},
        )

        # Set action_type metadata
        action._action_type = "connector"

        assert action._action_type == "connector"

    def test_ut_01_3_execute_not_implemented(self):
        """UT-01.3: Call execute() on base class without override, verify NotImplementedError raised."""

        # Cannot instantiate abstract class directly
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IntegrationAction(
                integration_id="test",
                action_id="test",
                settings={},
                credentials={},
            )

    def test_ut_01_4_action_type_defaults_to_none(self):
        """UT-01.4: Verify action_type defaults to None when not set."""

        class TestAction(IntegrationAction):
            async def execute(self, **kwargs):
                return {"status": "success"}

        action = TestAction(
            integration_id="test-integration",
            action_id="test-action",
            settings={},
            credentials={},
        )

        # Before setting, should be None
        assert action._action_type is None

    def test_context_injection(self):
        """Test execution context is properly injected and accessible."""

        class TestAction(IntegrationAction):
            async def execute(self, **kwargs):
                return {"status": "success"}

        ctx = {
            "tenant_id": "test-tenant",
            "job_id": "job-123",
            "run_id": "run-456",
            "task_id": "task-789",
            "workflow_id": "workflow-abc",
        }

        action = TestAction(
            integration_id="test-integration",
            action_id="test-action",
            settings={},
            credentials={},
            ctx=ctx,
        )

        # Verify context is stored
        assert action.ctx == ctx

        # Verify convenience properties work
        assert action.tenant_id == "test-tenant"
        assert action.job_id == "job-123"
        assert action.run_id == "run-456"

    def test_context_optional(self):
        """Test context is optional and defaults to empty dict."""

        class TestAction(IntegrationAction):
            async def execute(self, **kwargs):
                return {"status": "success"}

        action = TestAction(
            integration_id="test-integration",
            action_id="test-action",
            settings={},
            credentials={},
        )

        # Verify context defaults to empty dict
        assert action.ctx == {}
        assert action.tenant_id is None
        assert action.job_id is None
