"""
Tests for Cy 0.40.0 safe list indexing behavior.

List out-of-bounds access returns null instead of raising an error,
consistent with dict missing-key behavior. This enables
the `list[0] ?? default` pattern for safe access.
"""

from unittest.mock import AsyncMock

import pytest

from analysi.services.task_execution import DefaultTaskExecutor


def _make_executor():
    """Create a DefaultTaskExecutor with tool loaders stubbed out."""
    import asyncio

    executor = DefaultTaskExecutor()
    for method_name in (
        "_load_tools",
        "_load_time_functions",
        "_load_artifact_functions",
        "_load_llm_functions",
        "_load_ku_functions",
        "_load_task_functions",
        "_load_alert_functions",
        "_load_enrichment_functions",
        "_load_app_tools",
    ):
        method = getattr(executor, method_name, None)
        if method is None:
            continue
        if asyncio.iscoroutinefunction(method):
            setattr(executor, method_name, AsyncMock(return_value={}))
        else:
            from unittest.mock import MagicMock

            setattr(executor, method_name, MagicMock(return_value={}))
    return executor


def _ctx():
    """Minimal execution context."""
    return {
        "task_id": None,
        "task_run_id": "test",
        "tenant_id": "default",
        "app": "default",
        "cy_name": None,
        "workflow_run_id": None,
        "session": AsyncMock(),
        "directive": None,
    }


@pytest.mark.unit
class TestCySafeListIndexing:
    """Cy 0.40.0: list out-of-bounds returns null, enabling ?? operator."""

    @pytest.mark.asyncio
    async def test_oob_index_returns_null(self):
        """Accessing a list index out of bounds returns null (not an error)."""
        executor = _make_executor()
        result = await executor.execute(
            'items = ["a", "b"]\nreturn items[5]',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] is None

    @pytest.mark.asyncio
    async def test_oob_with_null_coalescing(self):
        """list[oob] ?? default returns the default value."""
        executor = _make_executor()
        result = await executor.execute(
            'items = ["a", "b"]\nreturn items[5] ?? "fallback"',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "fallback"

    @pytest.mark.asyncio
    async def test_empty_list_with_null_coalescing(self):
        """Empty list access with ?? returns the default."""
        executor = _make_executor()
        result = await executor.execute(
            "items = []\nreturn items[0] ?? {}",
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_valid_index_still_works(self):
        """Valid list index returns the element normally."""
        executor = _make_executor()
        result = await executor.execute(
            'items = ["a", "b", "c"]\nreturn items[1]',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "b"

    @pytest.mark.asyncio
    async def test_negative_index(self):
        """Negative index returns element from end of list."""
        executor = _make_executor()
        result = await executor.execute(
            'items = ["a", "b", "c"]\nreturn items[-1]',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "c"

    @pytest.mark.asyncio
    async def test_negative_oob_returns_null(self):
        """Negative out-of-bounds index returns null."""
        executor = _make_executor()
        result = await executor.execute(
            'items = ["a"]\nreturn items[-5] ?? "nope"',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "nope"

    @pytest.mark.asyncio
    async def test_dict_missing_key_still_returns_null(self):
        """Dict missing key returns null (unchanged behavior, for parity)."""
        executor = _make_executor()
        result = await executor.execute(
            'data = {"a": 1}\nreturn data.b ?? "missing"',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "missing"

    @pytest.mark.asyncio
    async def test_chained_safe_access(self):
        """Chained safe access with ?? on nested structures."""
        executor = _make_executor()
        result = await executor.execute(
            'data = {"items": []}\nreturn data.items[0] ?? "empty"',
            {},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "empty"

    @pytest.mark.asyncio
    async def test_input_field_with_null_coalescing(self):
        """Input field access with ?? works for missing fields."""
        executor = _make_executor()
        result = await executor.execute(
            'return input.missing_field ?? "default_value"',
            {"title": "test"},
            _ctx(),
        )
        assert result["status"] == "completed"
        assert result["output"] == "default_value"
