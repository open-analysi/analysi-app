"""Unit tests for execute_content_review ARQ job.

Critical: ARQ passes internal kwargs like _job_timeout through to the
function. The function signature must accept **kwargs to absorb them.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.alert_analysis.jobs.content_review import execute_content_review


def _mock_session_returning_none():
    """Create a mock async session where queries return no rows."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


class TestJobSignatureAcceptsArqKwargs:
    """ARQ passes _job_timeout, _job_id etc. as kwargs to the coroutine."""

    @pytest.mark.asyncio
    async def test_accepts_job_timeout_kwarg(self):
        """execute_content_review must accept _job_timeout without TypeError."""
        fake_review_id = "00000000-0000-0000-0000-000000000001"
        ctx: dict[str, Any] = {}
        mock_session = _mock_session_returning_none()

        with patch(
            "analysi.alert_analysis.jobs.content_review.AsyncSessionLocal"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            # This is what ARQ actually does — passes _job_timeout as kwarg
            result = await execute_content_review(
                ctx,
                fake_review_id,
                "test-tenant",
                "skill_validation",
                None,
                _job_timeout=900,
            )

            assert result["status"] == "not_found"
            assert result["review_id"] == fake_review_id

    @pytest.mark.asyncio
    async def test_accepts_multiple_arq_kwargs(self):
        """Should absorb any combination of ARQ internal kwargs."""
        fake_review_id = "00000000-0000-0000-0000-000000000002"
        ctx: dict[str, Any] = {}
        mock_session = _mock_session_returning_none()

        with patch(
            "analysi.alert_analysis.jobs.content_review.AsyncSessionLocal"
        ) as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await execute_content_review(
                ctx,
                fake_review_id,
                "test-tenant",
                "skill_validation",
                None,
                _job_timeout=900,
                _job_id="some-job-id",
                _queue_name="arq:queue",
            )

            assert result["status"] == "not_found"


class TestLlmSourcedFromIntegrations:
    """Content review job should get LLM from integrations, not env vars."""

    @pytest.mark.asyncio
    async def test_uses_langchain_factory_not_env_key(self):
        """Job should use LangChainFactory.get_primary_llm, not ANTHROPIC_API_KEY."""
        import inspect

        from analysi.alert_analysis.jobs.content_review import (
            execute_content_review,
        )

        source = inspect.getsource(execute_content_review)
        # Must NOT use create_langgraph_llm (reads ANTHROPIC_API_KEY)
        assert "create_langgraph_llm" not in source
        assert "ANTHROPIC_API_KEY" not in source
        # Must use LangChainFactory
        assert "LangChainFactory" in source
        assert "get_primary_llm" in source
