"""
LLM pricing registry for cost estimation.

Prices are per-million-tokens and sourced from public provider pricing pages.
All costs are in USD. Cost computation is best-effort — unknown models return
None rather than raising an error so that missing pricing never breaks execution.

Update as providers change their rates.
"""

from analysi.schemas.task_execution import LLMUsage

# ---------------------------------------------------------------------------
# Pricing table — (input_per_million_usd, output_per_million_usd)
# Keys are lowercased model name prefixes matched longest-first.
# ---------------------------------------------------------------------------

_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI — https://openai.com/api/pricing/
    "gpt-5.2-pro": (21.00, 168.00),
    "gpt-5.2-codex": (1.75, 14.00),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.1-codex-mini": (0.25, 2.00),
    "gpt-5.1-codex-max": (1.25, 10.00),
    "gpt-5.1-codex": (1.25, 10.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5-pro": (15.00, 120.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-codex": (1.25, 10.00),
    "gpt-5": (1.25, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o4-mini": (1.10, 4.40),
    "o3-pro": (20.00, 80.00),
    "o3-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "o1-pro": (150.00, 600.00),
    "o1-mini": (1.10, 4.40),
    "o1": (15.00, 60.00),
    # Anthropic — https://www.anthropic.com/pricing
    "claude-opus-4.6": (5.00, 25.00),
    "claude-opus-4.5": (5.00, 25.00),
    "claude-opus-4.1": (15.00, 75.00),
    "claude-sonnet-4.5": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4.5": (1.00, 5.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3-sonnet": (3.00, 15.00),
}


class LLMPricingRegistry:
    """Look up per-token cost for a given model name.

    Model name matching uses longest-prefix matching (case-insensitive) so that
    versioned names like "gpt-4o-2024-11-20" correctly match "gpt-4o".
    """

    def get_cost(
        self,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        """Compute total cost in USD for a single LLM call.

        Args:
            model: Model name string (e.g. "gpt-4o", "claude-3-5-sonnet-20241022").
                   None or empty string yields None (no pricing data).
            input_tokens: Number of prompt/input tokens consumed.
            output_tokens: Number of completion/output tokens produced.

        Returns:
            Estimated cost in USD, or None if model is unknown.
        """
        if not model:
            return None

        key = model.lower()
        # Find the longest matching prefix in the pricing table
        matched: tuple[float, float] | None = None
        best_len = -1
        for prefix, rates in _PRICING.items():
            if key.startswith(prefix) and len(prefix) > best_len:
                matched = rates
                best_len = len(prefix)

        if matched is None:
            return None

        input_per_m, output_per_m = matched
        return (input_tokens * input_per_m + output_tokens * output_per_m) / 1_000_000

    def compute_usage(
        self,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> LLMUsage:
        """Build a LLMUsage dataclass for one llm_run() call.

        Args:
            model: Model name string.
            input_tokens: Prompt token count.
            output_tokens: Completion token count.

        Returns:
            LLMUsage with totals and best-effort cost_usd.
        """
        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=self.get_cost(model, input_tokens, output_tokens),
        )


# Module-level singleton — import and use directly.
pricing_registry = LLMPricingRegistry()
