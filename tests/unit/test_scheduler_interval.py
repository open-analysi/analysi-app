"""Unit tests for scheduler interval computation (compute_next_run_at utility)."""

from datetime import UTC, datetime, timedelta

from analysi.scheduler.interval import compute_next_run_at


class TestComputeNextRunAt:
    """Tests for compute_next_run_at()."""

    # ── Positive tests ──────────────────────────────────────────────

    def test_compute_next_run_at_seconds(self):
        base = datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC)
        result = compute_next_run_at("every", "60s", from_time=base)
        assert result == base + timedelta(seconds=60)

    def test_compute_next_run_at_minutes(self):
        base = datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC)
        result = compute_next_run_at("every", "5m", from_time=base)
        assert result == base + timedelta(minutes=5)

    def test_compute_next_run_at_hours(self):
        base = datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC)
        result = compute_next_run_at("every", "1h", from_time=base)
        assert result == base + timedelta(hours=1)

    def test_compute_next_run_at_days(self):
        base = datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC)
        result = compute_next_run_at("every", "1d", from_time=base)
        assert result == base + timedelta(days=1)

    def test_compute_next_run_at_defaults_to_now(self):
        before = datetime.now(UTC)
        result = compute_next_run_at("every", "60s")
        after = datetime.now(UTC)
        assert result is not None
        # Should be ~60s from now (within a small tolerance)
        assert before + timedelta(seconds=59) <= result <= after + timedelta(seconds=61)

    def test_compute_next_run_at_with_every_prefix(self):
        base = datetime(2026, 3, 27, 12, 0, 0, tzinfo=UTC)
        result = compute_next_run_at("every", "every 30s", from_time=base)
        assert result == base + timedelta(seconds=30)

    # ── Negative tests ──────────────────────────────────────────────

    def test_compute_next_run_at_invalid_value(self):
        result = compute_next_run_at("every", "xyz")
        assert result is None

    def test_compute_next_run_at_empty_string(self):
        result = compute_next_run_at("every", "")
        assert result is None

    def test_compute_next_run_at_unsupported_type(self):
        """Cron type is not supported in v1 — should return None."""
        result = compute_next_run_at("cron", "0 * * * *")
        assert result is None
