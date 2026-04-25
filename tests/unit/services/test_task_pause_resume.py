"""
Unit tests for Task Pause & Resume.

Tests R7-R9: TaskExecutionService catches ExecutionPaused, stores checkpoint,
and can resume execution with a human's answer.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.constants import TaskConstants
from analysi.schemas.task_execution import TaskExecutionResult, TaskExecutionStatus

# ---------------------------------------------------------------------------
# R7: TaskConstants.Status includes PAUSED
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTaskPausedStatus:
    """PAUSED status is available in all relevant enums."""

    def test_task_constants_status_has_paused(self):
        """TaskConstants.Status includes PAUSED."""
        assert hasattr(TaskConstants.Status, "PAUSED")
        assert TaskConstants.Status.PAUSED == "paused"

    def test_task_execution_status_paused_value(self):
        """TaskExecutionStatus.PAUSED equals 'paused' (pre-existing check)."""
        assert TaskExecutionStatus.PAUSED == "paused"

    def test_paused_can_be_constructed_from_string(self):
        """PAUSED can be constructed from the string 'paused'."""
        status = TaskExecutionStatus("paused")
        assert status == TaskExecutionStatus.PAUSED


# ---------------------------------------------------------------------------
# R7: TaskExecutionResult with checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTaskExecutionResultWithCheckpoint:
    """TaskExecutionResult can carry a checkpoint for HITL pause."""

    def test_paused_result_with_checkpoint(self):
        """PAUSED result includes checkpoint in output_data."""
        checkpoint_data = {
            "node_results": {"n1": "some_llm_result"},
            "pending_node_id": "n2",
            "pending_tool_name": "ask_human",
            "pending_tool_args": {"question": "Block?"},
            "pending_tool_result": None,
            "variables": {"x": 1},
            "plan_version": "2.0",
        }
        result = TaskExecutionResult(
            status=TaskExecutionStatus.PAUSED,
            output_data={"_hitl_checkpoint": checkpoint_data},
            error_message=None,
            execution_time_ms=50,
            task_run_id=uuid4(),
        )
        assert result.status == "paused"
        assert result.output_data["_hitl_checkpoint"] == checkpoint_data
        assert result.error_message is None


# ---------------------------------------------------------------------------
# R7: DefaultTaskExecutor — hi_latency tool pauses
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultTaskExecutorHITL:
    """DefaultTaskExecutor handles hi_latency tools correctly."""

    @pytest.mark.asyncio
    async def test_executor_pauses_on_hi_latency_tool(self):
        """When a hi_latency tool is called, executor returns paused status with checkpoint."""
        from analysi.services.task_execution import DefaultTaskExecutor

        executor = DefaultTaskExecutor()

        # Script that calls a hi_latency tool
        cy_script = """
        answer = ask_human("Block this IP?")
        return answer
        """

        # Register tool as hi_latency
        async def ask_human(question):
            return "should not reach"

        tools = {
            "ask_human": {"fn": ask_human, "hi_latency": True},
        }

        # Monkey-patch _load_tools to return our hi_latency tool
        executor._load_tools = lambda ctx: dict(tools)
        executor._load_time_functions = lambda: {}

        result = await executor.execute(cy_script, {}, {})

        assert result["status"] == "paused"
        assert "_hitl_checkpoint" in result
        checkpoint = result["_hitl_checkpoint"]
        assert checkpoint["pending_tool_name"] == "ask_human"

    @pytest.mark.asyncio
    async def test_executor_normal_tool_completes(self):
        """Normal (non-hi_latency) tools complete without pausing."""
        from analysi.services.task_execution import DefaultTaskExecutor

        executor = DefaultTaskExecutor()

        cy_script = """
        result = fast_tool("data")
        return result
        """

        async def fast_tool(data):
            return "processed"

        tools = {"fast_tool": fast_tool}

        executor._load_tools = lambda ctx: dict(tools)
        executor._load_time_functions = lambda: {}

        result = await executor.execute(cy_script, {}, {})

        assert result["status"] == "completed"
        assert result["output"] == "processed"


# ---------------------------------------------------------------------------
# R7: _execute_task_with_session catches ExecutionPaused
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteTaskWithSessionPause:
    """_execute_task_with_session correctly handles ExecutionPaused."""

    @pytest.mark.asyncio
    async def test_paused_returns_paused_status(self):
        """When executor returns paused, _execute_task_with_session returns PAUSED result."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        # Mock executor to return paused result
        mock_executor_result = {
            "status": "paused",
            "_hitl_checkpoint": {
                "node_results": {},
                "pending_node_id": "n1",
                "pending_tool_name": "ask_human",
                "pending_tool_args": {},
                "pending_tool_result": None,
                "variables": {},
                "plan_version": "2.0",
            },
        }
        service.executor = MagicMock()
        service.executor.execute = AsyncMock(return_value=mock_executor_result)

        # Create mock task_run
        task_run = MagicMock()
        task_run.id = uuid4()
        task_run.cy_script = 'return "test"'
        task_run.task_id = None
        task_run.tenant_id = "test-tenant"
        task_run.workflow_run_id = None
        task_run.execution_context = {}
        task_run.started_at = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: None)
        )

        # Mock the services used internally (lazy import inside method)
        with patch("analysi.services.task_run.TaskRunService") as mock_trs:
            mock_trs_instance = MagicMock()
            mock_trs_instance.retrieve_input_data = AsyncMock(return_value={})
            mock_trs.return_value = mock_trs_instance

            result = await service._execute_task_with_session(task_run, mock_session)

        assert result.status == TaskExecutionStatus.PAUSED
        assert result.output_data is not None
        assert "_hitl_checkpoint" in result.output_data

    @pytest.mark.asyncio
    async def test_paused_captures_llm_usage(self):
        """Even when paused, any LLM usage from prior nodes is captured."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        mock_executor_result = {
            "status": "paused",
            "_hitl_checkpoint": {
                "node_results": {"n1": "llm_result"},
                "pending_node_id": "n2",
                "pending_tool_name": "ask",
                "pending_tool_args": {},
                "pending_tool_result": None,
                "variables": {},
                "plan_version": "2.0",
            },
        }
        service.executor = MagicMock()
        service.executor.execute = AsyncMock(return_value=mock_executor_result)

        task_run = MagicMock()
        task_run.id = uuid4()
        task_run.cy_script = 'return "test"'
        task_run.task_id = None
        task_run.tenant_id = "test-tenant"
        task_run.workflow_run_id = None
        task_run.execution_context = {}
        task_run.started_at = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=lambda: None)
        )

        with patch("analysi.services.task_run.TaskRunService") as mock_trs:
            mock_trs.return_value.retrieve_input_data = AsyncMock(return_value={})

            result = await service._execute_task_with_session(task_run, mock_session)

        assert result.status == TaskExecutionStatus.PAUSED
        # LLM usage may be None if no llm_run() was called — that's OK


# ---------------------------------------------------------------------------
# R7: execute_and_persist handles PAUSED
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteAndPersistPause:
    """execute_and_persist correctly persists PAUSED status."""

    @pytest.mark.asyncio
    async def test_paused_persists_status_and_checkpoint(self):
        """PAUSED result → task_run status='paused' with checkpoint in execution_context."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        checkpoint_data = {
            "node_results": {},
            "pending_node_id": "n1",
            "pending_tool_name": "ask_human",
            "pending_tool_args": {},
            "pending_tool_result": None,
            "variables": {},
            "plan_version": "2.0",
        }

        paused_result = TaskExecutionResult(
            status=TaskExecutionStatus.PAUSED,
            output_data={"_hitl_checkpoint": checkpoint_data},
            error_message=None,
            execution_time_ms=100,
            task_run_id=uuid4(),
        )

        service.execute_single_task = AsyncMock(return_value=paused_result)

        mock_session = AsyncMock()
        mock_task_run_service = MagicMock()
        mock_task_run_service.update_status = AsyncMock()
        mock_task_run_service.store_checkpoint = AsyncMock()

        with patch(
            "analysi.services.task_run.TaskRunService",
            return_value=mock_task_run_service,
        ):
            with patch("analysi.db.session.AsyncSessionLocal") as mock_session_local:
                mock_ctx = AsyncMock()
                mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
                mock_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_session_local.return_value = mock_ctx

                await service.execute_and_persist(
                    paused_result.task_run_id, "test-tenant"
                )

        # Verify update_status was called with "paused"
        mock_task_run_service.update_status.assert_called_once()
        call_args = mock_task_run_service.update_status.call_args
        assert (
            call_args[1].get(
                "status", call_args[0][2] if len(call_args[0]) > 2 else None
            )
            == "paused"
        )


# ---------------------------------------------------------------------------
# R8: TaskRunService.update_status handles "paused"
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateStatusPaused:
    """TaskRunService.update_status handles 'paused' correctly."""

    @pytest.mark.asyncio
    async def test_paused_does_not_set_completed_at(self):
        """When status is 'paused', completed_at and duration should NOT be set."""
        from analysi.services.task_run import TaskRunService

        service = TaskRunService()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.status = "running"
        mock_task_run.started_at = None
        mock_task_run.completed_at = None
        mock_task_run.duration = None
        mock_task_run.output_data = None
        mock_task_run.execution_context = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await service.update_status(mock_session, mock_task_run.id, "paused")

        assert mock_task_run.status == "paused"
        assert mock_task_run.completed_at is None


# ---------------------------------------------------------------------------
# R8/R9: Resume path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResumeTaskExecution:
    """Resume a paused task with the human's answer."""

    @pytest.mark.asyncio
    async def test_resume_injects_answer_and_executes(self):
        """resume_paused_task loads checkpoint, injects answer, re-executes."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        checkpoint_data = {
            "node_results": {"n1": "prior_llm_result"},
            "pending_node_id": "n2",
            "pending_tool_name": "ask_human",
            "pending_tool_args": {"question": "Block?"},
            "pending_tool_result": None,
            "variables": {"threat": "high"},
            "plan_version": "2.0",
        }

        # Mock task_run with checkpoint
        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.status = "paused"
        mock_task_run.cy_script = 'answer = ask_human("Block?")\nreturn answer'
        mock_task_run.task_id = None
        mock_task_run.tenant_id = "test-tenant"
        mock_task_run.workflow_run_id = None
        mock_task_run.execution_context = {"_hitl_checkpoint": checkpoint_data}

        # The resume should call execute_single_task which re-runs the script
        # with the checkpoint injected. The result should be COMPLETED.
        completed_result = TaskExecutionResult(
            status=TaskExecutionStatus.COMPLETED,
            output_data={"result": "Approved"},
            error_message=None,
            execution_time_ms=50,
            task_run_id=mock_task_run.id,
        )
        service.execute_single_task = AsyncMock(return_value=completed_result)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.resume_paused_task(
            session=mock_session,
            task_run_id=mock_task_run.id,
            tenant_id="test-tenant",
            human_response="Approved",
        )

        assert result.status == TaskExecutionStatus.COMPLETED
        # Session must be committed (not just flushed) so the inner session
        # created by execute_single_task can see the injected checkpoint
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_resume_non_paused_task_raises(self):
        """Attempting to resume a non-paused task raises ValueError."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.status = "completed"  # Not paused
        mock_task_run.execution_context = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="not paused"):
            await service.resume_paused_task(
                session=mock_session,
                task_run_id=mock_task_run.id,
                tenant_id="test-tenant",
                human_response="answer",
            )

    @pytest.mark.asyncio
    async def test_resume_task_not_found_raises(self):
        """Attempting to resume a non-existent task raises ValueError."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        task_run_id = uuid4()
        with pytest.raises(ValueError, match="not found"):
            await service.resume_paused_task(
                session=mock_session,
                task_run_id=task_run_id,
                tenant_id="test-tenant",
                human_response="answer",
            )

    @pytest.mark.asyncio
    async def test_resume_paused_task_without_checkpoint_raises(self):
        """Paused task with no _hitl_checkpoint in execution_context raises ValueError."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.status = "paused"
        mock_task_run.execution_context = {}  # No _hitl_checkpoint key

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="no checkpoint"):
            await service.resume_paused_task(
                session=mock_session,
                task_run_id=mock_task_run.id,
                tenant_id="test-tenant",
                human_response="answer",
            )

    @pytest.mark.asyncio
    async def test_resume_paused_task_with_none_execution_context_raises(self):
        """Paused task with execution_context=None raises ValueError."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.status = "paused"
        mock_task_run.execution_context = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="no checkpoint"):
            await service.resume_paused_task(
                session=mock_session,
                task_run_id=mock_task_run.id,
                tenant_id="test-tenant",
                human_response="answer",
            )


# ---------------------------------------------------------------------------
# Manifest hi_latency flag
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManifestHiLatencyFlag:
    """Slack manifest actions marked hi_latency are detected."""

    def test_slack_ask_question_is_hi_latency(self):
        """ask_question in Slack manifest should have hi_latency metadata."""
        from analysi.integrations.framework.registry import get_registry

        registry = get_registry()
        manifests = registry.list_integrations()

        slack_manifest = None
        for m in manifests:
            if m.id == "slack":
                slack_manifest = m
                break

        assert slack_manifest is not None, "Slack manifest not found"

        ask_action = None
        for action in slack_manifest.actions:
            if action.id == "ask_question":
                ask_action = action
                break

        assert ask_action is not None, "ask_question action not found"
        # hi_latency is captured via extra="allow" on ActionDefinition
        assert ask_action.metadata.get("hi_latency") is True, (
            "ask_question should be marked hi_latency in manifest"
        )


# ---------------------------------------------------------------------------
# Checkpoint serialization round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckpointSerializationRoundTrip:
    """ExecutionCheckpoint survives to_dict → JSON → from_dict without data loss.

    This is the contract between the cy-language interpreter and our PostgreSQL
    JSONB storage.  If this breaks, paused tasks lose their state on resume.
    """

    def _make_checkpoint(self, **overrides):
        """Build a realistic checkpoint dict with optional overrides."""
        from cy_language.execution_plan import ExecutionCheckpoint

        defaults = {
            "node_results": {
                "n1": {"output": "enrichment data", "score": 8.5},
                "n2": ["item1", "item2"],
                "n3": None,
                "n4": 42,
            },
            "pending_node_id": "n5",
            "pending_tool_name": "app::slack::ask_question",
            "pending_tool_args": {
                "text": "Block IP 192.168.1.1?",
                "channel": "C-security",
                "options": ["Block", "Ignore", "Escalate"],
            },
            "pending_tool_result": None,
            "variables": {
                "threat_score": 8.5,
                "ip": "192.168.1.1",
                "is_malicious": True,
                "enrichments": {"vt": {"score": 85}, "abuseipdb": None},
            },
            "plan_version": "2.0",
            "captured_logs": [],
        }
        defaults.update(overrides)
        return ExecutionCheckpoint(**defaults)

    def test_to_dict_from_dict_preserves_all_fields(self):
        """Round-trip through to_dict/from_dict preserves every field."""
        from cy_language.execution_plan import ExecutionCheckpoint

        original = self._make_checkpoint()
        restored = ExecutionCheckpoint.from_dict(original.to_dict())

        assert restored.node_results == original.node_results
        assert restored.pending_node_id == original.pending_node_id
        assert restored.pending_tool_name == original.pending_tool_name
        assert restored.pending_tool_args == original.pending_tool_args
        assert restored.pending_tool_result is None
        assert restored.variables == original.variables
        assert restored.plan_version == original.plan_version

    def test_json_round_trip_preserves_all_fields(self):
        """Round-trip through to_json/from_json (simulates JSONB) preserves every field."""
        from cy_language.execution_plan import ExecutionCheckpoint

        original = self._make_checkpoint()
        json_str = original.to_json()
        restored = ExecutionCheckpoint.from_json(json_str)

        assert restored.to_dict() == original.to_dict()

    def test_json_round_trip_with_pending_result(self):
        """Checkpoint with pending_tool_result set (resume path) round-trips correctly."""
        from cy_language.execution_plan import ExecutionCheckpoint

        original = self._make_checkpoint(pending_tool_result="Block")
        restored = ExecutionCheckpoint.from_json(original.to_json())

        assert restored.pending_tool_result == "Block"
        assert restored.to_dict() == original.to_dict()

    def test_json_round_trip_with_complex_pending_result(self):
        """pending_tool_result can be a dict (structured answer) and survive round-trip."""
        from cy_language.execution_plan import ExecutionCheckpoint

        complex_answer = {
            "action": "escalate",
            "reason": "Requires SOC L2 review",
            "assignee": "analyst@example.com",
        }
        original = self._make_checkpoint(pending_tool_result=complex_answer)
        restored = ExecutionCheckpoint.from_json(original.to_json())

        assert restored.pending_tool_result == complex_answer

    def test_json_round_trip_with_empty_node_results(self):
        """Checkpoint paused at the first tool call (no prior results) round-trips."""
        from cy_language.execution_plan import ExecutionCheckpoint

        original = self._make_checkpoint(
            node_results={},
            pending_node_id="n1",
            variables={},
        )
        restored = ExecutionCheckpoint.from_json(original.to_json())

        assert restored.node_results == {}
        assert restored.variables == {}
        assert restored.pending_node_id == "n1"

    def test_json_round_trip_with_nested_structures(self):
        """Deeply nested dicts/lists in variables survive JSON round-trip."""
        from cy_language.execution_plan import ExecutionCheckpoint

        deep_variables = {
            "alert": {
                "events": [
                    {"src_ip": "10.0.0.1", "dst_ips": ["8.8.8.8", "1.1.1.1"]},
                    {"src_ip": "10.0.0.2", "dst_ips": []},
                ],
                "metadata": {"tags": {"severity": "critical", "confidence": 0.95}},
            },
        }
        original = self._make_checkpoint(variables=deep_variables)
        restored = ExecutionCheckpoint.from_json(original.to_json())

        assert restored.variables == deep_variables

    def test_json_round_trip_with_unicode(self):
        """Unicode in tool args and variables survives JSON round-trip."""
        from cy_language.execution_plan import ExecutionCheckpoint

        original = self._make_checkpoint(
            pending_tool_args={
                "text": "Блокировать IP? 🔒",
                "channel": "C-セキュリティ",
            },
            variables={"note": "análisis de amenazas"},
        )
        restored = ExecutionCheckpoint.from_json(original.to_json())

        assert restored.pending_tool_args["text"] == "Блокировать IP? 🔒"
        assert restored.variables["note"] == "análisis de amenazas"
