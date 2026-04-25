"""Unit test conftest — eliminate real retry waits.

Tenacity retry decorators use wait_exponential with 1-2 second minimums.
Unit tests mock all HTTP clients, so retry backoff is pure waste (~15s
across the suite). This fixture patches the wait strategy to return 0,
making retries instant without touching asyncio.sleep (which timeout
and timing tests depend on).
"""

import pytest
import tenacity


@pytest.fixture(autouse=True)
def _no_retry_waits(monkeypatch):
    """Make tenacity wait_exponential return 0 for all unit tests.

    Only affects tenacity retry waits. Direct asyncio.sleep calls
    (used by timeout tests, timing measurements) are unchanged.
    """
    monkeypatch.setattr(
        tenacity.wait_exponential, "__call__", lambda self, retry_state: 0
    )
