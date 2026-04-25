"""Pluggable stages for workflow generation.

This package provides a dependency injection pattern for workflow generation stages.

Usage:
    from analysi.agentic_orchestration.stages import StageStrategyProvider

    provider = StageStrategyProvider(executor=executor)
    stages = provider.get_stages()
"""

from .base import SDK_METRICS_KEY, StageStrategy
from .provider import StageStrategyProvider

__all__ = [
    "SDK_METRICS_KEY",
    # Protocol and constants
    "StageStrategy",
    # Provider
    "StageStrategyProvider",
]
