"""Tests for workflow assembly node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.agentic_orchestration.nodes.workflow_assembly import (
    WorkflowAssemblyResult,
    gather_all_cy_names,
    gather_cy_names_from_built,
    gather_cy_names_from_existing,
    generate_unique_workflow_name,
    parse_workflow_result,
    workflow_assembly_node,
)
from analysi.agentic_orchestration.observability import (
    StageExecutionMetrics,
)


class TestGatherCyNamesFromExisting:
    """Tests for gather_cy_names_from_existing function."""

    def test_gather_cy_names_from_existing_proposals(self):
        """Verify cy_names extracted from existing proposals."""
        proposals = [
            {"name": "Task 1", "designation": "existing", "cy_name": "vt_ip_check"},
            {"name": "Task 2", "designation": "existing", "cy_name": "abuse_ip"},
            {"name": "Task 3", "designation": "new"},  # No cy_name for new
        ]

        result = gather_cy_names_from_existing(proposals)

        assert result == ["vt_ip_check", "abuse_ip"]

    def test_gather_cy_names_excludes_non_existing(self):
        """Verify new and modify proposals are excluded."""
        proposals = [
            {"name": "Task 1", "designation": "new", "cy_name": "new_task"},
            {"name": "Task 2", "category": "modify", "cy_name": "mod_task"},
            {"name": "Task 3", "designation": "existing", "cy_name": "existing_task"},
        ]

        result = gather_cy_names_from_existing(proposals)

        assert result == ["existing_task"]

    def test_gather_cy_names_handles_missing_cy_name(self):
        """Verify proposals without cy_name are skipped."""
        proposals = [
            {"name": "Task 1", "designation": "existing", "cy_name": "valid"},
            {"name": "Task 2", "designation": "existing"},  # Missing cy_name
        ]

        result = gather_cy_names_from_existing(proposals)

        assert result == ["valid"]

    def test_gather_cy_names_handles_empty_list(self):
        """Verify empty list returns empty list."""
        result = gather_cy_names_from_existing([])
        assert result == []

    def test_gather_cy_names_handles_none(self):
        """Verify None input returns empty list."""
        result = gather_cy_names_from_existing(None)
        assert result == []


class TestGatherCyNamesFromBuilt:
    """Tests for gather_cy_names_from_built function."""

    def test_gather_cy_names_from_successful_builds(self):
        """Verify cy_names extracted from successful builds."""
        tasks_built = [
            {"success": True, "cy_name": "built_task_1", "task_id": "uuid-1"},
            {"success": True, "cy_name": "built_task_2", "task_id": "uuid-2"},
        ]

        result = gather_cy_names_from_built(tasks_built)

        assert result == ["built_task_1", "built_task_2"]

    def test_gather_cy_names_excludes_failed_builds(self):
        """Verify failed builds are excluded."""
        tasks_built = [
            {"success": True, "cy_name": "success_task", "task_id": "uuid-1"},
            {"success": False, "cy_name": None, "error": "Build failed"},
        ]

        result = gather_cy_names_from_built(tasks_built)

        assert result == ["success_task"]

    def test_gather_cy_names_handles_missing_cy_name_in_success(self):
        """Verify successful builds without cy_name are skipped."""
        tasks_built = [
            {"success": True, "cy_name": "valid", "task_id": "uuid-1"},
            {"success": True, "cy_name": None, "task_id": "uuid-2"},  # Missing
        ]

        result = gather_cy_names_from_built(tasks_built)

        assert result == ["valid"]

    def test_gather_cy_names_built_handles_empty_list(self):
        """Verify empty list returns empty list."""
        result = gather_cy_names_from_built([])
        assert result == []

    def test_gather_cy_names_built_handles_none(self):
        """Verify None input returns empty list."""
        result = gather_cy_names_from_built(None)
        assert result == []


class TestGatherAllCyNames:
    """Tests for gather_all_cy_names function."""

    def test_gather_all_combines_sources(self):
        """Verify cy_names from both sources are combined."""
        proposals = [
            {"name": "Existing 1", "designation": "existing", "cy_name": "existing_1"},
            {"name": "New 1", "designation": "new"},
        ]
        tasks_built = [
            {"success": True, "cy_name": "built_1", "task_id": "uuid"},
        ]

        result = gather_all_cy_names(proposals, tasks_built)

        assert "existing_1" in result
        assert "built_1" in result

    def test_gather_all_maintains_order(self):
        """Verify existing tasks come before built tasks."""
        proposals = [
            {"name": "Existing", "designation": "existing", "cy_name": "existing_task"},
        ]
        tasks_built = [
            {"success": True, "cy_name": "built_task", "task_id": "uuid"},
        ]

        result = gather_all_cy_names(proposals, tasks_built)

        # Existing should come first
        assert result == ["existing_task", "built_task"]

    def test_gather_all_handles_empty_both(self):
        """Verify empty inputs return empty list."""
        result = gather_all_cy_names([], [])
        assert result == []

    def test_gather_all_handles_none_both(self):
        """Verify None inputs return empty list."""
        result = gather_all_cy_names(None, None)
        assert result == []


class TestWorkflowAssemblyResult:
    """Tests for WorkflowAssemblyResult class."""

    def test_workflow_assembly_result_to_dict_success(self):
        """Verify successful result serializes correctly."""
        result = WorkflowAssemblyResult(
            success=True,
            workflow_id="uuid-workflow",
            composition=["task1", "task2"],
            error=None,
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["workflow_id"] == "uuid-workflow"
        assert d["composition"] == ["task1", "task2"]
        assert d["error"] is None

    def test_workflow_assembly_result_to_dict_failure(self):
        """Verify failed result serializes correctly."""
        result = WorkflowAssemblyResult(
            success=False,
            workflow_id=None,
            composition=["task1"],
            error="Type validation failed",
        )

        d = result.to_dict()

        assert d["success"] is False
        assert d["workflow_id"] is None
        assert d["error"] == "Type validation failed"


class TestParseWorkflowResult:
    """Tests for parse_workflow_result function."""

    def test_parse_workflow_result_valid_json(self):
        """Verify valid JSON is parsed correctly."""
        json_str = json.dumps(
            {
                "workflow_id": "uuid-123",
                "status": "success",
                "composition": ["task1", "task2"],
                "error": None,
            }
        )

        result = parse_workflow_result(json_str)

        assert result["workflow_id"] == "uuid-123"
        assert result["status"] == "success"
        assert result["composition"] == ["task1", "task2"]

    def test_parse_workflow_result_invalid_json(self):
        """Verify invalid JSON returns error dict."""
        result = parse_workflow_result("not valid json {")

        assert "error" in result

    def test_parse_workflow_result_none(self):
        """Verify None input returns error dict."""
        result = parse_workflow_result(None)

        assert "error" in result


class TestWorkflowAssemblyNode:
    """Tests for workflow_assembly_node function."""

    @pytest.fixture(autouse=True)
    def _mock_generate_workflow_name(self):
        """Mock generate_unique_workflow_name to avoid DB calls in unit tests."""
        with patch(
            "analysi.agentic_orchestration.nodes.workflow_assembly.generate_unique_workflow_name",
            new_callable=AsyncMock,
            return_value="Test Alert Analysis Workflow",
        ):
            yield

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor."""
        executor = MagicMock()
        return executor

    @pytest.fixture
    def base_state(self):
        """Base state with required fields."""
        # Create mock workspace
        mock_workspace = MagicMock()
        mock_workspace.run_agent = AsyncMock(
            return_value=(
                {"workflow-result.json": None},
                StageExecutionMetrics(
                    duration_ms=0,
                    duration_api_ms=0,
                    num_turns=0,
                    total_cost_usd=0.0,
                    usage={},
                    tool_calls=[],
                ),
            )
        )
        mock_workspace.cleanup = MagicMock()

        return {
            "alert": {"id": "test-alert-001", "title": "Test Alert"},
            "runbook": "# Test Runbook\n\nInvestigation steps...",
            "run_id": "test-run-uuid",
            "tenant_id": "test-tenant",
            "task_proposals": [
                {
                    "name": "Existing Task",
                    "designation": "existing",
                    "cy_name": "existing_task",
                },
            ],
            "tasks_built": [
                {"success": True, "cy_name": "built_task", "task_id": "uuid-1"},
            ],
            "metrics": [],
            "error": None,
            "workspace": mock_workspace,
        }

    @pytest.mark.asyncio
    async def test_workflow_assembly_success(self, mock_executor, base_state):
        """Verify successful workflow assembly."""
        # Override workspace mock for this test
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": json.dumps(
                        {
                            "workflow_id": "uuid-workflow",
                            "status": "success",
                            "composition": ["existing_task", "built_task"],
                            "error": None,
                        }
                    )
                },
                StageExecutionMetrics(
                    duration_ms=3000,
                    duration_api_ms=2500,
                    num_turns=2,
                    total_cost_usd=0.03,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        result = await workflow_assembly_node(base_state, mock_executor)

        assert result["workflow_id"] == "uuid-workflow"
        assert result.get("workflow_error") is None
        assert result["workflow_composition"] == ["existing_task", "built_task"]

    @pytest.mark.asyncio
    async def test_workflow_assembly_handles_mcp_error(self, mock_executor, base_state):
        """Verify handling of MCP/agent errors."""
        # Override workspace mock - agent reports error
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": json.dumps(
                        {
                            "workflow_id": None,
                            "status": "error",
                            "composition": [],
                            "error": "Task 'missing_task' not found",
                        }
                    )
                },
                StageExecutionMetrics(
                    duration_ms=1000,
                    duration_api_ms=800,
                    num_turns=1,
                    total_cost_usd=0.01,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        result = await workflow_assembly_node(base_state, mock_executor)

        assert result["workflow_id"] is None
        assert "not found" in result["workflow_error"]

    @pytest.mark.asyncio
    async def test_workflow_assembly_test_failed_but_workflow_created(
        self, mock_executor, base_state
    ):
        """Verify workflow_id is returned even when test execution fails.

        Scenario: Workflow was created successfully, but the test execution
        failed (e.g., integration not configured). We should still return
        the workflow_id since the workflow itself is valid.

        This tests the fix for the bug where test failures were incorrectly
        treated as creation failures.
        """
        # Override workspace mock - workflow created but test failed
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": json.dumps(
                        {
                            "workflow_id": "uuid-workflow-created",
                            "status": "error",  # Test failed
                            "composition": ["task1", "task2"],
                            "error": "Workflow execution failed at node n4 (virustotal_ioc). Integration not configured.",
                            "test_status": "failed",
                        }
                    )
                },
                StageExecutionMetrics(
                    duration_ms=5000,
                    duration_api_ms=4500,
                    num_turns=3,
                    total_cost_usd=0.05,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        result = await workflow_assembly_node(base_state, mock_executor)

        # Critical: workflow_id should be returned even though test failed
        assert result["workflow_id"] == "uuid-workflow-created"
        # Error should NOT be set when workflow was created
        assert result.get("workflow_error") is None
        assert result["workflow_composition"] == ["task1", "task2"]

    @pytest.mark.asyncio
    async def test_workflow_assembly_handles_validation_error(
        self, mock_executor, base_state
    ):
        """Verify handling of type validation errors."""
        # Override workspace mock - validation error
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": json.dumps(
                        {
                            "workflow_id": None,
                            "status": "error",
                            "composition": ["task1", "task2"],
                            "error": "Type mismatch: task1 output incompatible with task2 input",
                        }
                    )
                },
                StageExecutionMetrics(
                    duration_ms=2000,
                    duration_api_ms=1800,
                    num_turns=2,
                    total_cost_usd=0.02,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        result = await workflow_assembly_node(base_state, mock_executor)

        assert result["workflow_id"] is None
        assert "Type mismatch" in result["workflow_error"]

    @pytest.mark.asyncio
    async def test_workflow_assembly_empty_tasks(self, mock_executor, base_state):
        """Verify handling when no tasks are available."""
        base_state["task_proposals"] = []
        base_state["tasks_built"] = []

        result = await workflow_assembly_node(base_state, mock_executor)

        assert result["workflow_id"] is None
        assert "no tasks" in result["workflow_error"].lower()

    @pytest.mark.asyncio
    async def test_workflow_assembly_only_failed_builds(
        self, mock_executor, base_state
    ):
        """Verify handling when all builds failed and no existing tasks."""
        base_state["task_proposals"] = [
            {"name": "New Task", "designation": "new"},  # No existing
        ]
        base_state["tasks_built"] = [
            {"success": False, "cy_name": None, "error": "Build failed"},
        ]

        result = await workflow_assembly_node(base_state, mock_executor)

        assert result["workflow_id"] is None
        assert "no tasks" in result["workflow_error"].lower()

    @pytest.mark.asyncio
    async def test_workflow_assembly_early_exit_on_error(
        self, mock_executor, base_state
    ):
        """Verify node skips processing if state has error."""
        base_state["error"] = "Previous stage failed"

        # Workspace should not be called when early exit occurs
        result = await workflow_assembly_node(base_state, mock_executor)

        # Verify workspace.run_agent was never called
        base_state["workspace"].run_agent.assert_not_called()
        assert result["workflow_id"] is None

    @pytest.mark.asyncio
    async def test_workflow_assembly_accumulates_metrics(
        self, mock_executor, base_state
    ):
        """Verify metrics are accumulated."""
        base_state["metrics"] = []

        # Override workspace mock
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": json.dumps(
                        {
                            "workflow_id": "uuid-workflow",
                            "status": "success",
                            "composition": ["task1"],
                            "error": None,
                        }
                    )
                },
                StageExecutionMetrics(
                    duration_ms=3000,
                    duration_api_ms=2500,
                    num_turns=2,
                    total_cost_usd=0.03,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        result = await workflow_assembly_node(base_state, mock_executor)

        assert "metrics" in result
        assert len(result["metrics"]) == 1

    @pytest.mark.asyncio
    async def test_workflow_assembly_calls_callback(self, mock_executor, base_state):
        """Verify callback is called appropriately."""
        mock_callback = AsyncMock()

        # Override workspace mock
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {
                    "workflow-result.json": json.dumps(
                        {
                            "workflow_id": "uuid-workflow",
                            "status": "success",
                            "composition": ["task1"],
                            "error": None,
                        }
                    )
                },
                StageExecutionMetrics(
                    duration_ms=3000,
                    duration_api_ms=2500,
                    num_turns=2,
                    total_cost_usd=0.03,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        await workflow_assembly_node(base_state, mock_executor, callback=mock_callback)

        mock_callback.on_stage_start.assert_called()

    @pytest.mark.asyncio
    async def test_workflow_assembly_handles_missing_output(
        self, mock_executor, base_state
    ):
        """Verify handling when agent doesn't produce output file."""
        # Override workspace mock - no output file
        base_state["workspace"].run_agent = AsyncMock(
            return_value=(
                {"workflow-result.json": None},  # Missing
                StageExecutionMetrics(
                    duration_ms=2000,
                    duration_api_ms=1800,
                    num_turns=2,
                    total_cost_usd=0.02,
                    usage={},
                    tool_calls=[],
                ),
            )
        )

        result = await workflow_assembly_node(base_state, mock_executor)

        assert result["workflow_id"] is None
        assert result["workflow_error"] is not None


class TestGenerateUniqueWorkflowName:
    """Tests for generate_unique_workflow_name function."""

    @pytest.mark.asyncio
    async def test_generates_base_name_when_no_existing(self):
        """Verify base name is used when no existing workflows."""
        with patch("analysi.db.AsyncSessionLocal") as mock_session_local:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []  # No existing workflows

            mock_session = AsyncMock()
            mock_session.execute.return_value = mock_result

            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await generate_unique_workflow_name(
                tenant_id="test-tenant",
                rule_name="SQL Injection Attack",
            )

            assert result == "SQL Injection Attack Analysis Workflow"

    @pytest.mark.asyncio
    async def test_appends_number_when_base_name_exists(self):
        """Verify number is appended when base name exists."""
        with patch("analysi.db.AsyncSessionLocal") as mock_session_local:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("SQL Injection Attack Analysis Workflow",),  # Base name exists
            ]

            mock_session = AsyncMock()
            mock_session.execute.return_value = mock_result

            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await generate_unique_workflow_name(
                tenant_id="test-tenant",
                rule_name="SQL Injection Attack",
            )

            assert result == "SQL Injection Attack Analysis Workflow 2"

    @pytest.mark.asyncio
    async def test_finds_next_available_number(self):
        """Verify next available number is found when multiple exist."""
        with patch("analysi.db.AsyncSessionLocal") as mock_session_local:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("SQL Injection Attack Analysis Workflow",),
                ("SQL Injection Attack Analysis Workflow 2",),
                ("SQL Injection Attack Analysis Workflow 3",),
            ]

            mock_session = AsyncMock()
            mock_session.execute.return_value = mock_result

            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await generate_unique_workflow_name(
                tenant_id="test-tenant",
                rule_name="SQL Injection Attack",
            )

            assert result == "SQL Injection Attack Analysis Workflow 4"

    @pytest.mark.asyncio
    async def test_handles_gaps_in_numbers(self):
        """Verify handles gaps in numbering (uses max + 1)."""
        with patch("analysi.db.AsyncSessionLocal") as mock_session_local:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("SQL Injection Attack Analysis Workflow",),
                ("SQL Injection Attack Analysis Workflow 5",),  # Gap: 2, 3, 4 missing
            ]

            mock_session = AsyncMock()
            mock_session.execute.return_value = mock_result

            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await generate_unique_workflow_name(
                tenant_id="test-tenant",
                rule_name="SQL Injection Attack",
            )

            # Uses max(5) + 1 = 6, not 2 (to avoid confusion)
            assert result == "SQL Injection Attack Analysis Workflow 6"

    @pytest.mark.asyncio
    async def test_handles_unknown_rule_name(self):
        """Verify handles default rule name."""
        with patch("analysi.db.AsyncSessionLocal") as mock_session_local:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []

            mock_session = AsyncMock()
            mock_session.execute.return_value = mock_result

            mock_session_local.return_value.__aenter__.return_value = mock_session

            result = await generate_unique_workflow_name(
                tenant_id="test-tenant",
                rule_name="Unknown Rule",
            )

            assert result == "Unknown Rule Analysis Workflow"
