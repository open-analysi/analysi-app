"""Tests for timeout alignment between ARQ job timeout and stuck alert detection.

These invariants prevent silent data loss:
- Stuck alert detection must fire after ARQ job timeout
- Orphan detection must be faster than stuck alert detection

The pipeline timeout chain:
    ARQ JOB_TIMEOUT (60 min)
     └─ Step 1: pre_triage           ~0s
     └─ Step 2: workflow_builder     ~1s
     └─ Step 3: workflow_execution   bounded by ARQ job timeout
     └─ Step 4: disposition_update   ~2s
    Stuck alert detection             60 min (must be ≥ JOB_TIMEOUT)
    Orphan detection                  2 min  (must be < stuck detection)
"""

from unittest.mock import patch

import pytest

from analysi.alert_analysis.config import AlertAnalysisConfig


class TestTimeoutAlignment:
    """Verify timeout config values are internally consistent."""

    def test_env_test_job_timeout_is_sufficient(self):
        """ALERT_WORKER_TIMEOUT from .env.test must be > 300.

        JOB_TIMEOUT must be > 300 so WORKFLOW_EXECUTION_POLL_TIMEOUT is positive
        and the overall timeout chain has sufficient buffer for non-execution steps.
        """
        assert AlertAnalysisConfig.JOB_TIMEOUT > 300, (
            f"JOB_TIMEOUT is {AlertAnalysisConfig.JOB_TIMEOUT}s (from ALERT_WORKER_TIMEOUT env var). "
            "Must be > 300 so WORKFLOW_EXECUTION_POLL_TIMEOUT is positive. "
            "Check .env.test ALERT_WORKER_TIMEOUT value."
        )

    def test_poll_timeout_derived_from_job_timeout(self):
        """Poll timeout should be JOB_TIMEOUT minus 300s buffer."""
        # This works regardless of env — tests the formula, not the value
        expected = AlertAnalysisConfig.JOB_TIMEOUT - 300
        assert expected == AlertAnalysisConfig.WORKFLOW_EXECUTION_POLL_TIMEOUT

    def test_orphan_detection_faster_than_stuck_detection(self):
        """Orphan detection (no progress, 2 min) must be faster than stuck detection."""
        orphan_threshold_minutes = 2  # hardcoded in detect_orphaned_analyses
        assert (
            orphan_threshold_minutes < AlertAnalysisConfig.STUCK_ALERT_TIMEOUT_MINUTES
        )

    @pytest.mark.parametrize(
        ("job_timeout", "stuck_minutes"),
        [
            (3600, 60),  # Production defaults
            (1800, 30),  # 30-minute config
            (600, 10),  # Minimum reasonable config
        ],
    )
    def test_production_invariants_hold(self, job_timeout, stuck_minutes):
        """Key invariants hold for all reasonable production configurations."""
        poll_timeout = job_timeout - 300
        buffer = job_timeout - poll_timeout

        assert poll_timeout > 0, "Poll timeout must be positive"
        assert poll_timeout < job_timeout, (
            "Polling must finish before ARQ kills the job"
        )
        assert buffer >= 300, "Need at least 300s buffer for pipeline steps 1/2/4"
        assert stuck_minutes * 60 >= job_timeout, (
            "Stuck detection must fire after job timeout"
        )

    def test_validate_passes_with_production_defaults(self):
        """Production configuration (JOB_TIMEOUT=3600) passes validation."""
        with (
            patch.object(AlertAnalysisConfig, "JOB_TIMEOUT", 3600),
            patch.object(AlertAnalysisConfig, "WORKFLOW_EXECUTION_POLL_TIMEOUT", 3300),
            patch.object(AlertAnalysisConfig, "STUCK_ALERT_TIMEOUT_MINUTES", 60),
        ):
            AlertAnalysisConfig.validate_timeout_alignment()

    def test_validate_detects_poll_exceeding_job_timeout(self):
        """Validation should catch polling timeout >= job timeout."""
        with (
            patch.object(AlertAnalysisConfig, "JOB_TIMEOUT", 3600),
            patch.object(AlertAnalysisConfig, "WORKFLOW_EXECUTION_POLL_TIMEOUT", 3700),
            patch.object(AlertAnalysisConfig, "STUCK_ALERT_TIMEOUT_MINUTES", 60),
        ):
            with pytest.raises(ValueError, match="[Pp]oll timeout"):
                AlertAnalysisConfig.validate_timeout_alignment()

    def test_validate_detects_stuck_alert_too_short(self):
        """Validation should catch stuck detection shorter than job timeout."""
        with (
            patch.object(AlertAnalysisConfig, "JOB_TIMEOUT", 3600),
            patch.object(AlertAnalysisConfig, "WORKFLOW_EXECUTION_POLL_TIMEOUT", 3300),
            patch.object(AlertAnalysisConfig, "STUCK_ALERT_TIMEOUT_MINUTES", 1),
        ):
            with pytest.raises(ValueError, match="[Ss]tuck.*alert"):
                AlertAnalysisConfig.validate_timeout_alignment()

    def test_validate_detects_non_positive_poll_timeout(self):
        """Validation should catch non-positive poll timeout."""
        with patch.object(AlertAnalysisConfig, "WORKFLOW_EXECUTION_POLL_TIMEOUT", 0):
            with pytest.raises(ValueError, match="positive"):
                AlertAnalysisConfig.validate_timeout_alignment()


class TestWorkflowExecutionIsDirectDB:
    """Verify WorkflowExecutionStep uses direct DB calls, not REST polling.

    After the move from REST-based polling to direct DB execution, the step
    no longer has _monitor_workflow_completion or api_client. These tests
    guard against accidentally reintroducing the REST dependency.
    """

    def test_no_monitor_workflow_completion(self):
        """Step should NOT have _monitor_workflow_completion (removed polling)."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        assert not hasattr(WorkflowExecutionStep, "_monitor_workflow_completion"), (
            "WorkflowExecutionStep should not have _monitor_workflow_completion. "
            "Workflow execution now runs synchronously via direct DB calls."
        )

    def test_no_api_client(self):
        """Step should NOT reference BackendAPIClient (no REST dependency)."""
        from analysi.alert_analysis.steps import workflow_execution as mod

        assert not hasattr(mod, "BackendAPIClient"), (
            "workflow_execution module should not import BackendAPIClient. "
            "Execution is now direct via WorkflowExecutor service."
        )
