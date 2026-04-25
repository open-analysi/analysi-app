"""Simulate the Cy-boundary adapter for integration-action unit tests.

The production adapter (`services/task_execution.py`) normalizes integration
action results before Cy scripts see them:

- Errors (`status == "error"`) raise `RuntimeError` with type+message.
- Envelope keys (`status`, `timestamp`, `integration_id`, `action_id`) are stripped.
- When `data` is a dict, siblings are merged in (data keys win on conflict).
- When `data` is a list or scalar, siblings are dropped.
- Otherwise the stripped dict is returned as-is (or the single remaining field
  unwrapped, for legacy single-field actions).

Integration-action tests SHOULD exercise the Cy-visible shape by piping raw
action output through `apply_cy_adapter(raw)` before asserting. Keeping this
logic in one place prevents drift between the production adapter and test
fixtures.
"""

from typing import Any

_ENVELOPE_KEYS = frozenset({"status", "timestamp", "integration_id", "action_id"})


def apply_cy_adapter(raw: Any) -> Any:
    """Return what a Cy script would see when calling `app::int::action(...)`.

    Mirrors `DefaultTaskExecutor._tool_wrapper` in `services/task_execution.py`.
    Raises `RuntimeError` for error results, matching production behavior.
    """
    if not isinstance(raw, dict):
        return raw

    if raw.get("status") == "error":
        error_msg = raw.get("error", "Unknown error")
        error_type = raw.get("error_type", "IntegrationError")
        raise RuntimeError(f"{error_type}: {error_msg}")

    if raw.get("status") != "success":
        return raw

    stripped = {k: v for k, v in raw.items() if k not in _ENVELOPE_KEYS}

    if "data" in stripped:
        payload = stripped.pop("data")
        if isinstance(payload, dict) and stripped:
            return {**stripped, **payload}
        return payload

    if len(stripped) == 1:
        return next(iter(stripped.values()))

    return stripped if stripped else raw
