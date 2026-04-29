"""
Unit tests for IntegrationLoader.

Tests UT-05.1 through UT-05.7 from TEST_PLAN.md
"""

import pytest

from analysi.integrations.framework.loader import IntegrationLoader


class TestIntegrationLoader:
    """Test IntegrationLoader dynamic loading functionality."""

    def test_ut_05_1_load_action_not_implemented(self):
        """UT-05.1: Load action - placeholder test (requires actual integration)."""
        # This test requires an actual integration to exist in the filesystem
        # We'll implement this in integration tests instead
        pass

    def test_ut_05_2_load_nonexistent_integration(self):
        """UT-05.2: Load action with invalid integration id, verify failure surfaces as ValueError.

        Hyphens aren't valid Python identifier characters, so the safe-import
        guard rejects the constructed path before importlib is called. The
        loader should still surface a ``ValueError``.
        """
        loader = IntegrationLoader()

        with pytest.raises(
            ValueError,
            match="(Refusing to load|Failed to import) actions",
        ):
            import asyncio

            asyncio.run(
                loader.load_action(
                    integration_id="nonexistent-integration-12345",
                    action_id="health_check",
                    action_metadata={"type": "connector"},
                    settings={},
                    credentials={},
                )
            )

    def test_ut_05_2b_load_unsafe_integration_id_rejected(self):
        """Reject integration ids that escape the analysi.* namespace."""
        loader = IntegrationLoader()

        with pytest.raises(ValueError, match="Refusing to load"):
            import asyncio

            asyncio.run(
                loader.load_action(
                    # ``..os`` would build a non-identifier dotted path; the
                    # safe-import allowlist must refuse it.
                    integration_id="..os",
                    action_id="health_check",
                    action_metadata={"type": "connector"},
                    settings={},
                    credentials={},
                )
            )

    def test_ut_05_3_load_nonexistent_action_class(self):
        """UT-05.3: Load action with non-existent action class - placeholder test."""
        # This test requires a real integration with missing action class
        # We'll implement this in integration tests
        pass

    def test_ut_05_4_settings_credentials_injection(self):
        """UT-05.4: Load action and verify settings/credentials injected - placeholder test."""
        # This test requires a real integration
        # We'll implement this in integration tests
        pass

    def test_ut_05_5_action_type_from_metadata(self):
        """UT-05.5: Load action and verify action_type set from metadata - placeholder test."""
        # This test requires a real integration
        # We'll implement this in integration tests
        pass

    def test_ut_05_6_to_class_name_simple(self):
        """UT-05.6: Test _to_class_name() conversion (health_check → HealthCheckAction)."""
        loader = IntegrationLoader()

        assert loader._to_class_name("health_check") == "HealthCheckAction"

    def test_ut_05_7_to_class_name_with_underscores(self):
        """UT-05.7: Test _to_class_name() with underscores (lookup_ip → LookupIpAction)."""
        loader = IntegrationLoader()

        assert loader._to_class_name("lookup_ip") == "LookupIpAction"
        assert loader._to_class_name("pull_alerts") == "PullAlertsAction"
        assert loader._to_class_name("update_notable") == "UpdateNotableAction"
        assert loader._to_class_name("query_events") == "QueryEventsAction"
        assert loader._to_class_name("get_notable_events") == "GetNotableEventsAction"
