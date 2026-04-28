"""Unit tests for ``analysi.services.cy_sleep_functions``.

Tiny module — single async ``sleep`` method with input validation and a
safety cap. Pure unit-test territory; previous coverage was 35.3 %.

We patch ``asyncio.sleep`` at the module boundary so tests are instant.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from analysi.services import cy_sleep_functions
from analysi.services.cy_sleep_functions import CySleepFunctions


@pytest.fixture
def fake_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace ``asyncio.sleep`` with an AsyncMock so tests are instant."""
    mock = AsyncMock()
    monkeypatch.setattr(cy_sleep_functions.asyncio, "sleep", mock)
    return mock


# ── happy path ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sleep_returns_true_after_completion(fake_sleep: AsyncMock) -> None:
    cy = CySleepFunctions()
    result = await cy.sleep(1.5)
    assert result is True
    fake_sleep.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_sleep_accepts_int_seconds(fake_sleep: AsyncMock) -> None:
    cy = CySleepFunctions()
    assert await cy.sleep(2) is True
    fake_sleep.assert_awaited_once_with(2)


@pytest.mark.asyncio
async def test_sleep_zero_seconds_is_valid(fake_sleep: AsyncMock) -> None:
    """Zero-length sleep is allowed (e.g. yield to event loop)."""
    cy = CySleepFunctions()
    assert await cy.sleep(0) is True
    fake_sleep.assert_awaited_once_with(0)


# ── safety cap ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sleep_caps_long_durations(
    fake_sleep: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    cy = CySleepFunctions()
    # 10 minutes requested, capped at 5 minutes (300s).
    assert await cy.sleep(600) is True
    fake_sleep.assert_awaited_once_with(300)


@pytest.mark.asyncio
async def test_sleep_at_cap_no_log_warning(fake_sleep: AsyncMock) -> None:
    """Exactly at the cap is fine — no warning."""
    cy = CySleepFunctions()
    assert await cy.sleep(300) is True
    fake_sleep.assert_awaited_once_with(300)


# ── validation / error paths ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sleep_rejects_negative_seconds(fake_sleep: AsyncMock) -> None:
    cy = CySleepFunctions()
    with pytest.raises(ValueError, match="non-negative"):
        await cy.sleep(-1)
    fake_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_sleep_rejects_string_seconds(fake_sleep: AsyncMock) -> None:
    cy = CySleepFunctions()
    with pytest.raises(ValueError, match="must be a number"):
        await cy.sleep("five")  # type: ignore[arg-type]
    fake_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_sleep_rejects_none(fake_sleep: AsyncMock) -> None:
    cy = CySleepFunctions()
    with pytest.raises(ValueError, match="must be a number"):
        await cy.sleep(None)  # type: ignore[arg-type]
    fake_sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_sleep_accepts_bool_as_int_subtype(fake_sleep: AsyncMock) -> None:
    """``bool`` is a subclass of ``int`` in Python, so the type check passes.
    We document this rather than treat it as a bug — Cy callers shouldn't
    rely on it, but if they do it shouldn't crash."""
    cy = CySleepFunctions()
    assert await cy.sleep(True) is True  # 1-second sleep
    fake_sleep.assert_awaited_once_with(True)
