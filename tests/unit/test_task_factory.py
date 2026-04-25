"""
Unit tests for task factory — script generation and health check result processing.

Pure function tests (no DB).
"""

from analysi.services.task_factory import (
    generate_action_script,
    generate_alert_ingestion_script,
    generate_health_check_script,
    process_health_check_result,
)


class TestGenerateAlertIngestionScript:
    """Tests for generate_alert_ingestion_script()."""

    def test_contains_pull_alerts(self):
        """Script calls app::{type}::pull_alerts."""
        script = generate_alert_ingestion_script("splunk")
        assert "app::splunk::pull_alerts" in script

    def test_contains_alerts_to_ocsf(self):
        """Script calls app::{type}::alerts_to_ocsf."""
        script = generate_alert_ingestion_script("splunk")
        assert "app::splunk::alerts_to_ocsf" in script

    def test_contains_ingest_alerts(self):
        """Script calls ingest_alerts."""
        script = generate_alert_ingestion_script("splunk")
        assert "ingest_alerts" in script

    def test_contains_checkpoint_calls(self):
        """Script uses get_checkpoint and set_checkpoint."""
        script = generate_alert_ingestion_script("splunk")
        assert "get_checkpoint" in script
        assert "set_checkpoint" in script

    def test_contains_default_lookback(self):
        """Script uses default_lookback as fallback."""
        script = generate_alert_ingestion_script("splunk")
        assert "default_lookback" in script

    def test_different_integration_type(self):
        """Script uses the provided integration type."""
        script = generate_alert_ingestion_script("echo_edr")
        assert "app::echo_edr::pull_alerts" in script
        assert "app::echo_edr::alerts_to_ocsf" in script


class TestGenerateHealthCheckScript:
    """Tests for generate_health_check_script()."""

    def test_contains_health_check(self):
        """Script calls app::{type}::health_check."""
        script = generate_health_check_script("splunk")
        assert "app::splunk::health_check" in script

    def test_returns_result(self):
        """Script returns the health check result."""
        script = generate_health_check_script("splunk")
        assert "return" in script

    def test_different_integration_type(self):
        """Script uses the provided integration type."""
        script = generate_health_check_script("echo_edr")
        assert "app::echo_edr::health_check" in script


class TestGenerateActionScript:
    """Tests for generate_action_script() — generic action Cy script."""

    def test_calls_action_with_app_prefix(self):
        """Script calls app::{type}::{cy_name}."""
        script = generate_action_script("splunk", "sourcetype_discovery")
        assert "app::splunk::sourcetype_discovery" in script

    def test_returns_result(self):
        """Script returns the action result."""
        script = generate_action_script("splunk", "sourcetype_discovery")
        assert script.startswith("return ")

    def test_different_integration_type(self):
        """Script uses the provided integration type."""
        script = generate_action_script("echo_edr", "list_processes")
        assert "app::echo_edr::list_processes" in script

    def test_different_action(self):
        """Script uses the provided cy_name."""
        script = generate_action_script("splunk", "list_indexes")
        assert "app::splunk::list_indexes" in script


class TestProcessHealthCheckResult:
    """Tests for process_health_check_result()."""

    def test_completed_healthy(self):
        """completed + healthy=true -> healthy."""
        result = process_health_check_result("completed", {"healthy": True})
        assert result == "healthy"

    def test_completed_unhealthy(self):
        """completed + healthy=false -> unhealthy."""
        result = process_health_check_result("completed", {"healthy": False})
        assert result == "unhealthy"

    def test_completed_no_healthy_key(self):
        """completed + missing healthy key -> unhealthy."""
        result = process_health_check_result("completed", {"status": "ok"})
        assert result == "unhealthy"

    def test_failed(self):
        """failed -> unknown."""
        result = process_health_check_result("failed", None)
        assert result == "unknown"

    def test_other_status(self):
        """running/pending -> unknown."""
        result = process_health_check_result("running", None)
        assert result == "unknown"

    def test_none_result(self):
        """completed + None result -> unhealthy."""
        result = process_health_check_result("completed", None)
        assert result == "unhealthy"
