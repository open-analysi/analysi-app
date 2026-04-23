"""Unit tests for FeedbackRelevanceService (Project Zakynthos).

Tests caching logic, LLM fallback, and error handling with mocked
Valkey and LLM callable.
"""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.services.feedback_relevance import (
    RELEVANCE_CACHE_TTL,
    FeedbackRelevanceService,
    _cache_key,
)


class TestCacheKey:
    """Test the deterministic SHA256 cache key computation."""

    @pytest.mark.unit
    def test_same_input_produces_same_key(self):
        k1 = _cache_key("prompt A", "feedback X")
        k2 = _cache_key("prompt A", "feedback X")
        assert k1 == k2

    @pytest.mark.unit
    def test_different_input_produces_different_key(self):
        k1 = _cache_key("prompt A", "feedback X")
        k2 = _cache_key("prompt A", "feedback Y")
        assert k1 != k2

    @pytest.mark.unit
    def test_key_has_expected_prefix(self):
        key = _cache_key("p", "f")
        assert key.startswith("feedback_relevance:")


class TestCheckRelevance:
    """Test FeedbackRelevanceService.check_relevance."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self):
        """Valkey cache hit should return immediately without calling LLM."""
        valkey = AsyncMock()
        valkey.get = AsyncMock(return_value="1")

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock()

        result = await svc.check_relevance("p", "f", llm)

        assert result is True
        llm.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cache_hit_false(self):
        valkey = AsyncMock()
        valkey.get = AsyncMock(return_value="0")

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock()

        result = await svc.check_relevance("p", "f", llm)

        assert result is False
        llm.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cache_miss_calls_llm_and_caches(self):
        """Cache miss should call the LLM and cache the result."""
        valkey = AsyncMock()
        valkey.get = AsyncMock(return_value=None)
        valkey.set = AsyncMock()

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock(return_value="YES")

        result = await svc.check_relevance("prompt", "feedback", llm)

        assert result is True
        llm.assert_called_once()
        valkey.set.assert_called_once()
        # Verify TTL is passed
        call_kwargs = valkey.set.call_args
        assert (
            call_kwargs.kwargs.get("ex") == RELEVANCE_CACHE_TTL
            or call_kwargs[1].get("ex") == RELEVANCE_CACHE_TTL
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_returns_no_marks_not_relevant(self):
        valkey = AsyncMock()
        valkey.get = AsyncMock(return_value=None)
        valkey.set = AsyncMock()

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock(return_value="NO")

        result = await svc.check_relevance("prompt", "feedback", llm)

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_failure_defaults_to_not_relevant(self):
        """On LLM failure, default to not relevant (safe)."""
        valkey = AsyncMock()
        valkey.get = AsyncMock(return_value=None)
        valkey.set = AsyncMock()

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await svc.check_relevance("prompt", "feedback", llm)

        assert result is False
        # Should still cache the "not relevant" result
        valkey.set.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_valkey_skips_caching(self):
        """With no Valkey client, all calls go to LLM and caching is skipped."""
        svc = FeedbackRelevanceService(valkey_client=None)
        llm = AsyncMock(return_value="YES")

        result = await svc.check_relevance("p", "f", llm)

        assert result is True
        llm.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valkey_read_error_falls_through_to_llm(self):
        """If Valkey read fails, still call LLM."""
        valkey = AsyncMock()
        valkey.get = AsyncMock(side_effect=ConnectionError("Valkey unreachable"))
        valkey.set = AsyncMock()

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock(return_value="YES")

        result = await svc.check_relevance("p", "f", llm)

        assert result is True
        llm.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valkey_write_error_does_not_break(self):
        """If Valkey write fails, still return the LLM result."""
        valkey = AsyncMock()
        valkey.get = AsyncMock(return_value=None)
        valkey.set = AsyncMock(side_effect=ConnectionError("write fail"))

        svc = FeedbackRelevanceService(valkey_client=valkey)
        llm = AsyncMock(return_value="YES")

        result = await svc.check_relevance("p", "f", llm)

        assert result is True


class TestGetRelevantFeedback:
    """Test filtering feedback entries by relevance."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_entries_returns_empty(self):
        svc = FeedbackRelevanceService(valkey_client=None)
        llm = AsyncMock()

        result = await svc.get_relevant_feedback("prompt", [], llm)

        assert result == []
        llm.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_filters_to_relevant_only(self):
        svc = FeedbackRelevanceService(valkey_client=None)

        # First feedback relevant, second not
        call_count = 0

        async def mock_llm(prompt):
            nonlocal call_count
            call_count += 1
            return "YES" if call_count == 1 else "NO"

        result = await svc.get_relevant_feedback(
            "prompt", ["good feedback", "irrelevant feedback"], mock_llm
        )

        assert result == ["good feedback"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_relevant(self):
        svc = FeedbackRelevanceService(valkey_client=None)
        llm = AsyncMock(return_value="YES")

        result = await svc.get_relevant_feedback("prompt", ["a", "b"], llm)

        assert result == ["a", "b"]


class TestFactory:
    """Test the async factory method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_returns_instance_on_valkey_failure(self):
        """Factory should return a working instance even if Valkey is unavailable."""
        with patch("analysi.services.feedback_relevance.redis.Redis") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=ConnectionError("no valkey"))
            mock_redis.return_value = mock_client

            svc = await FeedbackRelevanceService.create()

            # Should have no Valkey client (graceful degradation)
            assert svc._valkey is None
