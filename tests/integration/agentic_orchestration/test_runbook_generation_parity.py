"""Integration tests for SDK/LangGraph runbook generation parity.

Verify both implementations produce equivalent output structure.

These tests verify:
1. SDK implementation output structure
2. LangGraph implementation output structure
3. Feature flag dispatch works correctly
4. Metrics are collected properly
5. Callbacks are invoked correctly
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.nodes.runbook_generation import (
    _use_langgraph,
    runbook_generation_node,
)
from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
    WorkflowGenerationStage,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestOutputStructureParity:
    """Test that both implementations return the same output structure."""

    @pytest.fixture
    def sample_alert(self):
        """Sample NAS alert for testing."""
        return {
            "id": "test-alert-123",
            "title": "SQL Injection Detected in Login Form",
            "severity": "high",
            "source_event_id": "evt-456",
            "detection_rule": "sql_injection_detection",
            "raw_alert": {"original": "data"},
        }

    @pytest.fixture
    def mock_sdk_workspace(self):
        """Mock workspace for SDK path."""
        workspace = AsyncMock()
        workspace.work_dir = "/tmp/test-workspace"
        mock_metrics = MagicMock(spec=StageExecutionMetrics)
        mock_metrics.duration_ms = 1500
        mock_metrics.duration_api_ms = 1200
        mock_metrics.num_turns = 3
        mock_metrics.total_cost_usd = 0.05
        mock_metrics.usage = {"input_tokens": 5000, "output_tokens": 2000}
        mock_metrics.tool_calls = []

        workspace.run_agent = AsyncMock(
            return_value=(
                {
                    "matched-runbook.md": "# SQL Injection Runbook\n\nContent here.",
                    "matching-report.json": '{"decision": "matched", "confidence": "HIGH"}',
                },
                mock_metrics,
            )
        )
        return workspace

    @pytest.fixture
    def mock_langgraph_result(self):
        """Mock result from LangGraph run_phase1."""
        return {
            "runbook": "# SQL Injection Runbook\n\nComposed content.",
            "matching_report": {
                "decision": "composed",
                "confidence": "MEDIUM",
                "score": 55,
                "composition_sources": ["runbook1.md", "runbook2.md"],
            },
        }

    @pytest.mark.asyncio
    async def test_sdk_output_has_required_fields(
        self, sample_alert, mock_sdk_workspace
    ):
        """SDK returns {runbook, matching_report, metrics}."""
        state = {
            "alert": sample_alert,
            "workspace": mock_sdk_workspace,
        }

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            result = await runbook_generation_node(state, AsyncMock())

        assert "runbook" in result
        assert "matching_report" in result
        assert "metrics" in result
        assert result["runbook"] is not None
        assert isinstance(result["metrics"], list)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_langgraph_output_has_required_fields(
        self, sample_alert, mock_langgraph_result
    ):
        """LangGraph returns {runbook, matching_report, metrics}."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.return_value = mock_langgraph_result
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            result = await runbook_generation_node(state, None)

        assert "runbook" in result
        assert "matching_report" in result
        assert "metrics" in result
        assert result["runbook"] is not None
        assert isinstance(result["metrics"], list)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_matching_report_is_json_string_from_langgraph(
        self, sample_alert, mock_langgraph_result
    ):
        """LangGraph matching_report is JSON string (not dict)."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.return_value = mock_langgraph_result
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            result = await runbook_generation_node(state, None)

        # matching_report should be a JSON string
        assert isinstance(result["matching_report"], str)

        # Should be valid JSON
        parsed = json.loads(result["matching_report"])
        assert parsed["decision"] == "composed"
        assert parsed["confidence"] == "MEDIUM"


@pytest.mark.asyncio
@pytest.mark.integration
class TestFeatureFlagDispatch:
    """Test that feature flag correctly dispatches to the right implementation."""

    @pytest.fixture
    def sample_alert(self):
        """Sample alert."""
        return {
            "title": "Test Alert",
            "severity": "high",
            "source_event_id": "test-123",
        }

    @pytest.mark.asyncio
    async def test_flag_false_uses_sdk(self, sample_alert):
        """ANALYSI_USE_LANGGRAPH_PHASE1=false uses SDK implementation."""
        mock_workspace = AsyncMock()
        mock_metrics = MagicMock(spec=StageExecutionMetrics)
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"matched-runbook.md": "# Runbook", "matching-report.json": "{}"},
                mock_metrics,
            )
        )

        state = {"alert": sample_alert, "workspace": mock_workspace}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            await runbook_generation_node(state, AsyncMock())

        # SDK path should call workspace.run_agent
        mock_workspace.run_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_flag_true_uses_langgraph(self, sample_alert):
        """ANALYSI_USE_LANGGRAPH_PHASE1=true uses LangGraph implementation."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.runbook_generation_node_langgraph"
            ) as mock_langgraph:
                mock_langgraph.return_value = {
                    "runbook": "# Runbook",
                    "matching_report": "{}",
                    "metrics": [],
                }

                await runbook_generation_node(state, None)

        # LangGraph path should be called
        mock_langgraph.assert_called_once()

    @pytest.mark.asyncio
    async def test_use_langgraph_function_values(self):
        """_use_langgraph() correctly parses environment variable."""
        # True cases
        for value in ["true", "TRUE", "True", " true "]:
            with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": value}):
                assert _use_langgraph() is True, f"Expected True for '{value}'"

        # False cases
        for value in ["false", "FALSE", "", "0", "1", "yes"]:
            with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": value}):
                assert _use_langgraph() is False, f"Expected False for '{value}'"

        # Not set
        env_without = {
            k: v for k, v in os.environ.items() if k != "ANALYSI_USE_LANGGRAPH_PHASE1"
        }
        with patch.dict(os.environ, env_without, clear=True):
            assert _use_langgraph() is False


@pytest.mark.asyncio
@pytest.mark.integration
class TestMetricsCollection:
    """Test that metrics are collected from both implementations."""

    @pytest.fixture
    def sample_alert(self):
        """Sample alert."""
        return {
            "title": "Test Alert",
            "severity": "high",
            "source_event_id": "test-123",
        }

    @pytest.mark.asyncio
    async def test_sdk_returns_stage_execution_metrics(self, sample_alert):
        """SDK returns StageExecutionMetrics in metrics list."""
        mock_workspace = AsyncMock()
        mock_metrics = StageExecutionMetrics(
            duration_ms=1500,
            duration_api_ms=1200,
            num_turns=3,
            total_cost_usd=0.05,
            usage={"input_tokens": 5000, "output_tokens": 2000},
            tool_calls=[],
        )
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"matched-runbook.md": "# Runbook", "matching-report.json": "{}"},
                mock_metrics,
            )
        )

        state = {"alert": sample_alert, "workspace": mock_workspace}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            result = await runbook_generation_node(state, AsyncMock())

        assert len(result["metrics"]) == 1
        metrics = result["metrics"][0]
        assert metrics.duration_ms == 1500
        assert metrics.num_turns == 3

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_langgraph_returns_stage_execution_metrics(self, sample_alert):
        """LangGraph returns StageExecutionMetrics in metrics list."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.return_value = {
                    "runbook": "# Runbook",
                    "matching_report": {"decision": "matched"},
                }
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            result = await runbook_generation_node(state, None)

        assert len(result["metrics"]) >= 1
        metrics = result["metrics"][0]
        assert isinstance(metrics, StageExecutionMetrics)
        assert hasattr(metrics, "duration_ms")
        assert hasattr(metrics, "num_turns")
        assert hasattr(metrics, "total_cost_usd")


@pytest.mark.asyncio
@pytest.mark.integration
class TestCallbackInvocation:
    """Test that ProgressCallback is invoked correctly."""

    @pytest.fixture
    def sample_alert(self):
        """Sample alert."""
        return {
            "title": "Test Alert",
            "severity": "high",
            "source_event_id": "test-123",
        }

    @pytest.fixture
    def mock_callback(self):
        """Mock ProgressCallback."""
        callback = AsyncMock()
        callback.on_stage_start = AsyncMock()
        callback.on_stage_complete = AsyncMock()
        callback.on_stage_error = AsyncMock()
        return callback

    @pytest.mark.asyncio
    async def test_sdk_calls_callback_on_start(self, sample_alert, mock_callback):
        """SDK calls on_stage_start."""
        mock_workspace = AsyncMock()
        mock_metrics = MagicMock(spec=StageExecutionMetrics)
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"matched-runbook.md": "# Runbook", "matching-report.json": "{}"},
                mock_metrics,
            )
        )

        state = {"alert": sample_alert, "workspace": mock_workspace}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            await runbook_generation_node(state, AsyncMock(), mock_callback)

        mock_callback.on_stage_start.assert_called_once()
        call_args = mock_callback.on_stage_start.call_args
        assert call_args[0][0] == WorkflowGenerationStage.RUNBOOK_GENERATION

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_langgraph_calls_callback_on_start(self, sample_alert, mock_callback):
        """LangGraph calls on_stage_start."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.return_value = {
                    "runbook": "# Runbook",
                    "matching_report": {"decision": "matched"},
                }
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            await runbook_generation_node(state, None, mock_callback)

        mock_callback.on_stage_start.assert_called_once()
        call_args = mock_callback.on_stage_start.call_args
        assert call_args[0][0] == WorkflowGenerationStage.RUNBOOK_GENERATION

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_langgraph_calls_callback_on_complete(
        self, sample_alert, mock_callback
    ):
        """LangGraph calls on_stage_complete on success."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.return_value = {
                    "runbook": "# Runbook",
                    "matching_report": {"decision": "matched"},
                }
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            await runbook_generation_node(state, None, mock_callback)

        mock_callback.on_stage_complete.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_langgraph_calls_callback_on_error(self, sample_alert, mock_callback):
        """LangGraph calls on_stage_error on failure."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.side_effect = RuntimeError("Graph failed")
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            result = await runbook_generation_node(
                                state, None, mock_callback
                            )

        # Error should be returned (not raised)
        assert result.get("error") is not None
        mock_callback.on_stage_error.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
class TestErrorHandling:
    """Test error handling in both implementations."""

    @pytest.fixture
    def sample_alert(self):
        """Sample alert."""
        return {
            "title": "Test Alert",
            "severity": "high",
            "source_event_id": "test-123",
        }

    @pytest.mark.asyncio
    async def test_sdk_error_returns_error_field(self, sample_alert):
        """SDK errors are caught and returned as {error: msg}."""
        mock_workspace = AsyncMock()
        mock_workspace.run_agent = AsyncMock(side_effect=RuntimeError("SDK failed"))

        state = {"alert": sample_alert, "workspace": mock_workspace}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "false"}):
            result = await runbook_generation_node(state, AsyncMock())

        assert "error" in result
        assert result["runbook"] is None

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="LangGraph experimental path - get_runbooks_repository_path removed"
    )
    async def test_langgraph_error_returns_error_field(self, sample_alert):
        """LangGraph errors are caught and returned as {error: msg}."""
        state = {"alert": sample_alert, "tenant_id": "test-tenant"}

        with patch.dict(os.environ, {"ANALYSI_USE_LANGGRAPH_PHASE1": "true"}):
            with patch(
                "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.run_phase1"
            ) as mock_run:
                mock_run.side_effect = RuntimeError("LangGraph failed")
                with patch(
                    "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.create_langgraph_llm"
                ):
                    with patch(
                        "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_db_skills_store"
                    ):
                        with patch(
                            "analysi.agentic_orchestration.nodes.runbook_generation_langgraph.get_runbooks_repository_path"
                        ):
                            result = await runbook_generation_node(state, None)

        assert "error" in result
        assert result["runbook"] is None
        assert "LangGraph" in result["error"]
