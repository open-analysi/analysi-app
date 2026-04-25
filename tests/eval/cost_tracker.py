"""Eval cost tracker — automatic LLM cost collection across test sessions.

Tracks costs from two sources automatically (no test code changes needed):
1. Claude Agent SDK — via execute_stage() interception
2. LangChain ChatAnthropic — via ainvoke()/agenerate() interception

Also supports manual recording for any other LLM provider.

Usage (automatic — just run tests):
    pytest -m eval tests/eval/

Usage (manual, for non-standard LLM calls):
    def test_custom(eval_cost_tracker):
        # ... make LLM call ...
        eval_cost_tracker.record(cost_usd=0.05, label="custom call")
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# Pricing per million tokens (Claude Sonnet 4 / 2025 pricing)
# Update these when model pricing changes.
_PRICE_PER_M = {
    "input": 3.00,
    "output": 15.00,
    "cache_read": 0.30,
    "cache_creation": 3.75,
}


def _estimate_cost(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Estimate cost from token counts using current pricing."""
    return (
        input_tokens * _PRICE_PER_M["input"]
        + output_tokens * _PRICE_PER_M["output"]
        + cache_read_tokens * _PRICE_PER_M["cache_read"]
        + cache_creation_tokens * _PRICE_PER_M["cache_creation"]
    ) / 1_000_000


@dataclass
class CostEntry:
    """Single LLM cost record."""

    source: str  # e.g. "sdk" or "langchain" or "manual"
    label: str  # e.g. "test_ao_basic::test_basic_connectivity"
    cost_usd: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_s: float = 0.0


@dataclass
class EvalCostTracker:
    """Session-wide cost aggregator for eval tests.

    Thread-safe — the SDK subprocess transport may call back from threads.
    """

    entries: list[CostEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # Set by autouse fixture so interceptors know which test is running
    current_test: str = ""

    # ── Public API ──────────────────────────────────────────────

    def record(
        self,
        *,
        cost_usd: float,
        label: str = "",
        source: str = "manual",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        duration_s: float = 0.0,
    ) -> None:
        """Record a cost entry. Thread-safe."""
        entry = CostEntry(
            source=source,
            label=label or self.current_test or "unknown",
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
            duration_s=duration_s,
        )
        with self._lock:
            self.entries.append(entry)

    def record_sdk_metrics(self, metrics: object, label: str = "") -> None:
        """Extract cost from a StageExecutionMetrics object."""
        usage = getattr(metrics, "usage", {}) or {}
        self.record(
            source="sdk",
            label=label,
            cost_usd=getattr(metrics, "total_cost_usd", 0.0) or 0.0,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
        )

    def record_langchain_usage(
        self, usage_metadata: dict, duration_s: float = 0.0, label: str = ""
    ) -> None:
        """Extract cost from a LangChain AIMessage.usage_metadata dict."""
        inp = usage_metadata.get("input_tokens", 0)
        out = usage_metadata.get("output_tokens", 0)
        cache_read = usage_metadata.get("input_token_details", {}).get("cache_read", 0)
        cache_creation = usage_metadata.get("input_token_details", {}).get(
            "cache_creation", 0
        )
        self.record(
            source="langchain",
            label=label,
            cost_usd=_estimate_cost(inp, out, cache_read, cache_creation),
            input_tokens=inp,
            output_tokens=out,
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
            duration_s=duration_s,
        )

    # ── Aggregation ─────────────────────────────────────────────

    @property
    def total_cost(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self.entries)

    @property
    def total_cache_read_tokens(self) -> int:
        return sum(e.cache_read_tokens for e in self.entries)

    @property
    def total_cache_creation_tokens(self) -> int:
        return sum(e.cache_creation_tokens for e in self.entries)

    # ── Terminal Report ─────────────────────────────────────────

    def summary(self) -> str:
        """Generate formatted cost summary for pytest terminal."""
        if not self.entries:
            return "  No LLM costs recorded.\n"

        lines: list[str] = []

        # Group by test label for cleaner output
        by_label: dict[str, list[CostEntry]] = {}
        for e in self.entries:
            by_label.setdefault(e.label, []).append(e)

        # Header
        lines.append(
            f"  {'Test':<58} {'Cost':>8}  {'In':>7}  {'Out':>7}  {'Cache R':>8}  {'Cache W':>8}"
        )
        lines.append("  " + "\u2500" * 102)

        # Per-test rows
        for label, group in by_label.items():
            cost = sum(e.cost_usd for e in group)
            inp = sum(e.input_tokens for e in group)
            out = sum(e.output_tokens for e in group)
            cr = sum(e.cache_read_tokens for e in group)
            cw = sum(e.cache_creation_tokens for e in group)

            # Truncate long labels
            short = label if len(label) <= 57 else label[:54] + "..."
            lines.append(
                f"  {short:<58} ${cost:>6.4f}  {inp:>7,}  {out:>7,}  {cr:>8,}  {cw:>8,}"
            )

        # Totals
        lines.append("  " + "\u2500" * 102)
        lines.append(
            f"  {'TOTAL (' + str(len(self.entries)) + ' calls)':<58} "
            f"${self.total_cost:>6.4f}  "
            f"{self.total_input_tokens:>7,}  "
            f"{self.total_output_tokens:>7,}  "
            f"{self.total_cache_read_tokens:>8,}  "
            f"{self.total_cache_creation_tokens:>8,}"
        )
        lines.append("")

        return "\n".join(lines)


# ── Interceptors ────────────────────────────────────────────────


def install_sdk_interceptor(tracker: EvalCostTracker) -> None:
    """Monkey-patch AgentOrchestrationExecutor.execute_stage to auto-record costs.

    Every SDK query() call will be recorded without any test code changes.
    """
    try:
        from analysi.agentic_orchestration.sdk_wrapper import (
            AgentOrchestrationExecutor,
        )
    except ImportError:
        return  # SDK not available

    original = AgentOrchestrationExecutor.execute_stage

    async def _tracked_execute_stage(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        t0 = time.monotonic()
        result_text, metrics = await original(self, *args, **kwargs)
        elapsed = time.monotonic() - t0

        # Build a label from stage + context_id
        stage = args[0] if args else kwargs.get("stage", "unknown")
        ctx = kwargs.get("context_id", "")
        label = tracker.current_test or "fixture"
        if ctx:
            label = f"{label} [{stage}:{ctx}]"

        usage = getattr(metrics, "usage", {}) or {}
        tracker.record(
            source="sdk",
            label=label,
            cost_usd=getattr(metrics, "total_cost_usd", 0.0) or 0.0,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            duration_s=elapsed,
        )
        return result_text, metrics

    AgentOrchestrationExecutor.execute_stage = _tracked_execute_stage  # type: ignore[assignment]
    AgentOrchestrationExecutor._original_execute_stage = original  # type: ignore[attr-defined]


def install_langchain_interceptor(tracker: EvalCostTracker) -> None:
    """Monkey-patch ChatAnthropic.ainvoke to auto-record costs.

    Every LangChain Anthropic call will be recorded without any test code changes.
    """
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        return

    original = ChatAnthropic.ainvoke

    async def _tracked_ainvoke(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        t0 = time.monotonic()
        result = await original(self, *args, **kwargs)
        elapsed = time.monotonic() - t0

        usage = getattr(result, "usage_metadata", None)
        if usage:
            tracker.record_langchain_usage(
                usage,
                duration_s=elapsed,
                label=tracker.current_test or "fixture",
            )
        return result

    ChatAnthropic.ainvoke = _tracked_ainvoke  # type: ignore[assignment]
    ChatAnthropic._original_ainvoke = original  # type: ignore[attr-defined]


def uninstall_interceptors() -> None:
    """Restore original methods."""
    try:
        from analysi.agentic_orchestration.sdk_wrapper import (
            AgentOrchestrationExecutor,
        )

        orig = getattr(AgentOrchestrationExecutor, "_original_execute_stage", None)
        if orig:
            AgentOrchestrationExecutor.execute_stage = orig  # type: ignore[assignment]
    except ImportError:
        pass

    try:
        from langchain_anthropic import ChatAnthropic

        orig = getattr(ChatAnthropic, "_original_ainvoke", None)
        if orig:
            ChatAnthropic.ainvoke = orig  # type: ignore[assignment]
    except ImportError:
        pass
