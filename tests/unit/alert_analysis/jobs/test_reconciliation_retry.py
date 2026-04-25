"""Unit tests for reconciliation job retry logic."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.alert_analysis.jobs.reconciliation import (
    should_retry_workflow_generation,
)
from analysi.models.alert import AlertAnalysis


class TestShouldRetryWorkflowGeneration:
    """Test should_retry_workflow_generation() helper function."""

    def _make_analysis(
        self,
        retry_count: int = 0,
        last_failure_at: datetime | None = None,
    ) -> MagicMock:
        """Create a mock AlertAnalysis with specified retry tracking fields."""
        analysis = MagicMock(spec=AlertAnalysis)
        analysis.workflow_gen_retry_count = retry_count
        analysis.workflow_gen_last_failure_at = last_failure_at
        return analysis

    def test_returns_true_on_first_attempt(self):
        """First attempt should always be allowed."""
        analysis = self._make_analysis(retry_count=0, last_failure_at=None)

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is True
        assert "OK" in reason
        assert "retry 1/" in reason

    def test_returns_true_when_retry_count_below_max(self):
        """Retries should be allowed when count is below max."""
        max_retries = AlertAnalysisConfig.MAX_WORKFLOW_GEN_RETRIES

        # Test with retry count = 1 (second attempt)
        analysis = self._make_analysis(
            retry_count=1,
            last_failure_at=datetime.now(UTC) - timedelta(hours=1),  # Past backoff
        )

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is True
        assert "OK" in reason
        assert f"retry 2/{max_retries}" in reason

    def test_returns_false_after_max_retries(self):
        """Retry should be denied after max retries exceeded."""
        max_retries = AlertAnalysisConfig.MAX_WORKFLOW_GEN_RETRIES

        analysis = self._make_analysis(
            retry_count=max_retries,
            last_failure_at=datetime.now(UTC) - timedelta(hours=1),
        )

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is False
        assert "Max retries" in reason
        assert str(max_retries) in reason

    def test_returns_false_during_backoff_period(self):
        """Retry should be denied during backoff period."""
        # First failure (retry_count=0), backoff = 5 minutes
        # Set last_failure_at to 1 minute ago
        analysis = self._make_analysis(
            retry_count=0,
            last_failure_at=datetime.now(UTC) - timedelta(minutes=1),
        )

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is False
        assert "Backoff active" in reason

    def test_returns_true_after_backoff_period(self):
        """Retry should be allowed after backoff period expires."""
        # First failure (retry_count=0), backoff = 5 minutes
        # Set last_failure_at to 6 minutes ago (past backoff)
        analysis = self._make_analysis(
            retry_count=0,
            last_failure_at=datetime.now(UTC) - timedelta(minutes=6),
        )

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is True
        assert "OK" in reason

    def test_exponential_backoff_calculation(self):
        """Backoff should increase exponentially: 5min, 10min, 20min."""
        base = AlertAnalysisConfig.WORKFLOW_GEN_BACKOFF_BASE_MINUTES

        # Test each retry level
        test_cases = [
            (0, base),  # First retry: 5 minutes
            (1, base * 2),  # Second retry: 10 minutes
            (2, base * 4),  # Third retry: 20 minutes
        ]

        for retry_count, expected_backoff_minutes in test_cases:
            # Set last_failure_at to just before backoff expires
            just_before_backoff = datetime.now(UTC) - timedelta(
                minutes=expected_backoff_minutes - 1
            )
            analysis = self._make_analysis(
                retry_count=retry_count,
                last_failure_at=just_before_backoff,
            )

            should_retry, reason = should_retry_workflow_generation(analysis)

            assert should_retry is False, (
                f"Should NOT retry for retry_count={retry_count} "
                f"with backoff={expected_backoff_minutes}min, 1 min before expiry"
            )

            # Set last_failure_at to just after backoff expires
            just_after_backoff = datetime.now(UTC) - timedelta(
                minutes=expected_backoff_minutes + 1
            )
            analysis = self._make_analysis(
                retry_count=retry_count,
                last_failure_at=just_after_backoff,
            )

            should_retry, reason = should_retry_workflow_generation(analysis)

            assert should_retry is True, (
                f"Should retry for retry_count={retry_count} "
                f"with backoff={expected_backoff_minutes}min, 1 min after expiry"
            )

    def test_handles_none_retry_count(self):
        """Should treat None retry_count as 0."""
        analysis = self._make_analysis()
        analysis.workflow_gen_retry_count = None

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is True
        assert "retry 1/" in reason

    def test_handles_none_last_failure(self):
        """Should allow retry when last_failure_at is None (no previous failure)."""
        analysis = self._make_analysis(retry_count=1, last_failure_at=None)

        should_retry, reason = should_retry_workflow_generation(analysis)

        # Should be allowed since no backoff can be calculated without last_failure_at
        assert should_retry is True

    def test_reason_includes_wait_time_during_backoff(self):
        """Reason should include wait time when backoff is active."""
        analysis = self._make_analysis(
            retry_count=0,
            last_failure_at=datetime.now(UTC) - timedelta(minutes=2),
        )

        should_retry, reason = should_retry_workflow_generation(analysis)

        assert should_retry is False
        assert "wait" in reason.lower()
        assert "s" in reason  # seconds in wait time
