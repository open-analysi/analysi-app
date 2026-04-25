"""Feedback Relevance Service — Project Zakynthos.

Checks whether analyst feedback is relevant to a given LLM prompt.
Results are cached in Valkey to avoid redundant LLM calls.
"""

import hashlib
import os
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as redis

from analysi.config.logging import get_logger
from analysi.config.valkey_db import ValkeyDBConfig

logger = get_logger(__name__)

# Relevance check prompt template
RELEVANCE_PROMPT_TEMPLATE = """You are evaluating if analyst feedback is relevant to a task prompt.

TASK PROMPT:
{prompt}

ANALYST FEEDBACK:
{feedback_text}

Is this feedback relevant to the task prompt above? Answer only YES or NO."""

# Cache TTL: 1 hour
RELEVANCE_CACHE_TTL = int(os.getenv("ANALYSI_FEEDBACK_RELEVANCE_CACHE_TTL", 3600))


def _cache_key(prompt: str, feedback_text: str) -> str:
    """Compute Valkey cache key for a prompt+feedback pair."""
    content = f"{prompt}\n---\n{feedback_text}"
    digest = hashlib.sha256(content.encode()).hexdigest()
    return f"feedback_relevance:{digest}"


class FeedbackRelevanceService:
    """Check if feedback entries are relevant to a given prompt, with caching."""

    def __init__(self, valkey_client: redis.Redis | None = None) -> None:
        """Initialize with an optional Valkey client.

        If no client is provided, caching is disabled (every call hits the LLM).
        """
        self._valkey = valkey_client

    @classmethod
    async def create(cls) -> "FeedbackRelevanceService":
        """Factory that connects to the CACHE_DB Valkey instance."""
        try:
            settings = ValkeyDBConfig.get_redis_settings(ValkeyDBConfig.CACHE_DB)
            client = redis.Redis(
                host=settings.host,
                port=settings.port,
                db=settings.database,
                password=settings.password,
                decode_responses=True,
            )
            # Quick connectivity check
            await client.ping()
            return cls(valkey_client=client)
        except Exception as e:
            logger.warning(
                "valkey_connection_failed_for_feedback_relevance", error=str(e)
            )
            return cls(valkey_client=None)

    async def check_relevance(
        self,
        prompt: str,
        feedback_text: str,
        llm_callable: Callable[..., Coroutine[Any, Any, str]],
    ) -> bool:
        """Check if a single feedback entry is relevant to a prompt.

        Args:
            prompt: The LLM prompt being executed.
            feedback_text: The feedback to check.
            llm_callable: An async callable that takes a prompt string and returns a response string.

        Returns:
            True if the feedback is relevant to the prompt.
        """
        key = _cache_key(prompt, feedback_text)

        # Check cache
        if self._valkey is not None:
            try:
                cached = await self._valkey.get(key)
                if cached is not None:
                    logger.debug("feedback_relevance_cache_hit", key=key[:40])
                    return cached == "1"
            except Exception as e:
                logger.warning("feedback_relevance_cache_read_error", error=str(e))

        # Cache miss — ask the LLM
        relevance_prompt = RELEVANCE_PROMPT_TEMPLATE.format(
            prompt=prompt,
            feedback_text=feedback_text,
        )
        try:
            response = await llm_callable(relevance_prompt)
            is_relevant = response.strip().upper().startswith("YES")
        except Exception as e:
            logger.warning("feedback_relevance_llm_check_failed", error=str(e))
            # On LLM failure, assume not relevant (safe default — don't inject unknown feedback)
            is_relevant = False

        # Cache the result
        if self._valkey is not None:
            try:
                await self._valkey.set(
                    key, "1" if is_relevant else "0", ex=RELEVANCE_CACHE_TTL
                )
                logger.debug(
                    "feedback_relevance_cache_set", key=key[:40], relevant=is_relevant
                )
            except Exception as e:
                logger.warning("feedback_relevance_cache_write_error", error=str(e))

        return is_relevant

    async def get_relevant_feedback(
        self,
        prompt: str,
        feedback_entries: list[str],
        llm_callable: Callable[..., Coroutine[Any, Any, str]],
    ) -> list[str]:
        """Filter feedback entries to only those relevant to the prompt.

        Args:
            prompt: The LLM prompt being executed.
            feedback_entries: List of feedback text strings.
            llm_callable: An async callable for relevance checks.

        Returns:
            List of feedback texts that are relevant.
        """
        if not feedback_entries:
            return []

        relevant = []
        for entry in feedback_entries:
            if await self.check_relevance(prompt, entry, llm_callable):
                relevant.append(entry)

        if relevant:
            logger.info(
                "feedback_relevance_results",
                total=len(feedback_entries),
                relevant=len(relevant),
            )

        return relevant
