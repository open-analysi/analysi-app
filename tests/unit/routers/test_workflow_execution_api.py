"""
Unit tests for workflow execution API — llm_usage field population.

Verifies that both GET /workflow-runs (list) and GET /workflow-runs/{id}
(detail) correctly populate the llm_usage field from execution_context["_llm_usage"].
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.routers.workflow_execution import _llm_usage_from_run
from analysi.schemas.task_run import LLMUsageResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_request():
    """Create a mock Request with request_id for api_response()."""
    req = MagicMock()
    req.state.request_id = "test-request-id"
    return req


def _make_run(
    execution_context: dict | None = None, workflow_name: str = "Test Workflow"
):
    """Build a minimal WorkflowRun-like object (plain MagicMock)."""
    run = MagicMock()
    run.id = uuid4()
    run.tenant_id = "test-tenant"
    run.workflow_id = uuid4()
    run.workflow_name = workflow_name
    run.status = "completed"
    run.started_at = datetime.now(UTC)
    run.completed_at = datetime.now(UTC)
    run.input_location = None
    run.output_location = None
    run.error_message = None
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    run.execution_context = execution_context
    return run


# ---------------------------------------------------------------------------
# _llm_usage_from_run helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLlmUsageFromRun:
    """Unit tests for the _llm_usage_from_run() router helper."""

    def test_returns_none_when_execution_context_is_none(self):
        run = _make_run(execution_context=None)
        assert _llm_usage_from_run(run) is None

    def test_returns_none_when_execution_context_is_empty(self):
        run = _make_run(execution_context={})
        assert _llm_usage_from_run(run) is None

    def test_returns_none_when_llm_usage_key_missing(self):
        run = _make_run(execution_context={"analysis_id": "abc"})
        assert _llm_usage_from_run(run) is None

    def test_returns_none_when_llm_usage_is_not_a_dict(self):
        run = _make_run(execution_context={"_llm_usage": "bad-value"})
        assert _llm_usage_from_run(run) is None

    def test_returns_populated_response_for_valid_usage(self):
        run = _make_run(
            execution_context={
                "_llm_usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "cost_usd": 0.003,
                }
            }
        )
        result = _llm_usage_from_run(run)
        assert isinstance(result, LLMUsageResponse)
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150
        assert result.cost_usd == pytest.approx(0.003)

    def test_returns_zero_tokens_when_keys_missing_from_dict(self):
        """Partial _llm_usage dict defaults missing token fields to 0."""
        run = _make_run(execution_context={"_llm_usage": {"total_tokens": 42}})
        result = _llm_usage_from_run(run)
        assert result is not None
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.total_tokens == 42
        assert result.cost_usd is None

    def test_cost_usd_none_when_not_present(self):
        run = _make_run(
            execution_context={
                "_llm_usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                }
            }
        )
        result = _llm_usage_from_run(run)
        assert result is not None
        assert result.cost_usd is None

    def test_ignores_other_execution_context_keys(self):
        """Other keys in execution_context (e.g. analysis_id) must not interfere."""
        run = _make_run(
            execution_context={
                "analysis_id": "xyz-123",
                "_llm_usage": {
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "total_tokens": 280,
                    "cost_usd": 0.01,
                },
            }
        )
        result = _llm_usage_from_run(run)
        assert result is not None
        assert result.input_tokens == 200


# ---------------------------------------------------------------------------
# GET /workflow-runs/{id}  (detail endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetWorkflowRunEndpoint:
    """Test that the detail endpoint surfaces llm_usage from execution_context."""

    async def _call_get_workflow_run(self, workflow_run_mock):
        """Invoke get_workflow_run() with a mocked service."""
        from analysi.routers.workflow_execution import get_workflow_run

        mock_session = AsyncMock()
        mock_service = MagicMock()
        mock_service.get_workflow_run_details = AsyncMock(
            return_value=workflow_run_mock
        )

        with patch(
            "analysi.routers.workflow_execution.WorkflowExecutionService",
            return_value=mock_service,
        ):
            return await get_workflow_run(
                workflow_run_id=workflow_run_mock.id,
                request=_mock_request(),
                tenant_id="test-tenant",
                session=mock_session,
            )

    async def test_llm_usage_populated_when_data_present(self):
        run = _make_run(
            execution_context={
                "_llm_usage": {
                    "input_tokens": 300,
                    "output_tokens": 100,
                    "total_tokens": 400,
                    "cost_usd": 0.012,
                }
            }
        )
        result = await self._call_get_workflow_run(run)
        assert result.data.llm_usage is not None
        assert result.data.llm_usage.input_tokens == 300
        assert result.data.llm_usage.output_tokens == 100
        assert result.data.llm_usage.total_tokens == 400
        assert result.data.llm_usage.cost_usd == pytest.approx(0.012)

    async def test_llm_usage_is_none_when_no_execution_context(self):
        run = _make_run(execution_context=None)
        result = await self._call_get_workflow_run(run)
        assert result.data.llm_usage is None

    async def test_llm_usage_is_none_when_execution_context_has_no_usage_key(self):
        run = _make_run(execution_context={"analysis_id": "abc"})
        result = await self._call_get_workflow_run(run)
        assert result.data.llm_usage is None

    async def test_returns_404_when_run_not_found(self):
        from fastapi import HTTPException

        from analysi.routers.workflow_execution import get_workflow_run

        mock_session = AsyncMock()
        mock_service = MagicMock()
        mock_service.get_workflow_run_details = AsyncMock(return_value=None)

        with patch(
            "analysi.routers.workflow_execution.WorkflowExecutionService",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_workflow_run(
                    workflow_run_id=uuid4(),
                    request=_mock_request(),
                    tenant_id="test-tenant",
                    session=mock_session,
                )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# GET /workflow-runs  (list endpoint)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestListWorkflowRunsEndpoint:
    """Test that the list endpoint includes llm_usage for each run."""

    async def _call_list_workflow_runs(self, runs: list, total: int = None):
        """Invoke list_workflow_runs() with a mocked repository."""
        from analysi.routers.workflow_execution import list_workflow_runs

        if total is None:
            total = len(runs)

        mock_session = AsyncMock()
        mock_repo = MagicMock()
        mock_repo.list_workflow_runs = AsyncMock(return_value=(runs, total))

        with patch(
            "analysi.routers.workflow_execution.WorkflowRunRepository",
            return_value=mock_repo,
        ):
            return await list_workflow_runs(
                request=_mock_request(),
                workflow_id=None,
                status=None,
                sort="created_at",
                order="desc",
                skip=0,
                limit=50,
                tenant_id="test-tenant",
                session=mock_session,
            )

    async def test_llm_usage_populated_for_runs_with_usage_data(self):
        run = _make_run(
            execution_context={
                "_llm_usage": {
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "total_tokens": 700,
                    "cost_usd": 0.021,
                }
            }
        )
        result = await self._call_list_workflow_runs([run])
        assert len(result.data) == 1
        usage = result.data[0].llm_usage
        assert usage is not None
        assert usage.input_tokens == 500
        assert usage.output_tokens == 200
        assert usage.total_tokens == 700
        assert usage.cost_usd == pytest.approx(0.021)

    async def test_llm_usage_is_none_for_runs_without_usage(self):
        run = _make_run(execution_context=None)
        result = await self._call_list_workflow_runs([run])
        assert len(result.data) == 1
        assert result.data[0].llm_usage is None

    async def test_mixed_runs_some_with_and_some_without_usage(self):
        run_with = _make_run(
            execution_context={
                "_llm_usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "cost_usd": None,
                }
            }
        )
        run_without = _make_run(execution_context={})

        result = await self._call_list_workflow_runs([run_with, run_without])
        assert len(result.data) == 2

        # Find which is which by presence of llm_usage
        usages = [r.llm_usage for r in result.data]
        assert any(u is not None for u in usages), (
            "At least one run should have llm_usage"
        )
        assert any(u is None for u in usages), (
            "At least one run should have no llm_usage"
        )

    async def test_total_and_pagination_fields_preserved(self):
        runs = [_make_run() for _ in range(3)]
        result = await self._call_list_workflow_runs(runs, total=99)
        assert result.meta.total == 99
        assert result.meta.limit == 50
        assert result.meta.offset == 0
        assert len(result.data) == 3

    async def test_empty_list_returns_zero_runs(self):
        result = await self._call_list_workflow_runs([], total=0)
        assert result.data == []
        assert result.meta.total == 0
