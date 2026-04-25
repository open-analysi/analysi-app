"""Configuration for LangGraph implementations.

Provides dependency injection for LLM and ResourceStore used by LangGraph phases.

NOTE: Skills are now DB-only. All skill access goes through
DatabaseResourceStore. Filesystem skills have been removed.
"""

import os
import warnings

from langchain_anthropic import ChatAnthropic

from analysi.agentic_orchestration.langgraph.skills.db_store import (
    DatabaseResourceStore,
)
from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Default model for LangGraph phases
DEFAULT_MODEL = "claude-sonnet-4-20250514"


def create_langgraph_llm(model: str = DEFAULT_MODEL) -> ChatAnthropic:
    """Create LangChain LLM from environment config.

    Note: This is a transitional function. Prefer LangChainFactory.get_primary_llm()
    for integration-based credentials.

    Args:
        model: Model name to use. Defaults to claude-sonnet-4-20250514.

    Returns:
        Configured ChatAnthropic instance.

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

    return ChatAnthropic(model_name=model, anthropic_api_key=api_key)  # type: ignore[call-arg]


def get_langgraph_llm(model: str = DEFAULT_MODEL) -> ChatAnthropic:
    """Create LangChain LLM from environment config.

    DEPRECATED: Use create_langgraph_llm() or LangChainFactory.get_primary_llm() instead.
    """
    warnings.warn(
        "get_langgraph_llm() is deprecated. Use LangChainFactory.get_primary_llm() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_langgraph_llm(model=model)


def get_db_skills_store(tenant_id: str) -> DatabaseResourceStore:
    """Create DatabaseResourceStore for skill lookups.

    All skill access is now database-backed for tenant isolation.
    Skills are installed per-tenant via content packs (e.g.,
    `analysi packs install foundation`). See docs/projects/delos.md.

    Args:
        tenant_id: Tenant identifier for skill lookups.

    Returns:
        Configured DatabaseResourceStore instance.
    """
    from analysi.db.session import AsyncSessionLocal

    return DatabaseResourceStore(
        session_factory=AsyncSessionLocal,
        tenant_id=tenant_id,
    )
