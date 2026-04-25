"""
Unit tests for legacy code cleanup validation.

Tests that verify all legacy connector code has been removed.
Following TDD - these tests will fail until legacy code is deleted.
"""

from pathlib import Path

import pytest


class TestLegacyCodeRemoval:
    """Test that legacy connector code has been removed."""

    def test_legacy_base_connector_removed(self):
        """Test: Legacy BaseConnector class removed.

        Goal: Verify legacy BaseConnector no longer exists in codebase.
        """
        # Try to import BaseConnector from legacy location
        with pytest.raises(ImportError):
            from analysi.integrations.connectors.base_connector import (
                BaseConnector,  # noqa: F401
            )

    def test_legacy_splunk_connector_removed(self):
        """Test: Legacy SplunkConnector removed.

        Goal: Ensure legacy SplunkConnector class deleted.
        """
        # Try to import SplunkConnector
        with pytest.raises(ImportError):
            from analysi.integrations.connectors.splunk_connector import (
                SplunkConnector,  # noqa: F401
            )

    def test_legacy_openai_connector_removed(self):
        """Test: Legacy OpenAIConnector removed.

        Goal: Ensure legacy OpenAIConnector class deleted.
        """
        # Try to import OpenAIConnector
        with pytest.raises(ImportError):
            from analysi.integrations.connectors.openai_connector import (
                OpenAIConnector,  # noqa: F401
            )

    def test_legacy_connectors_directory_removed(self):
        """Test: Legacy connectors directory removed.

        Goal: Verify entire src/analysi/integrations/connectors/ directory deleted.
        """
        connectors_dir = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "analysi"
            / "integrations"
            / "connectors"
        )

        # Directory should not exist or should be empty
        if connectors_dir.exists():
            # If it exists, should only contain __init__.py and __pycache__
            contents = list(connectors_dir.iterdir())
            non_cache_contents = [
                p for p in contents if p.name not in ["__pycache__", "__init__.py"]
            ]
            assert len(non_cache_contents) == 0, (
                f"Connectors directory should only have __init__.py, found: {non_cache_contents}"
            )

    def test_old_test_files_moved_or_deleted(self):
        """Test: Old test files moved/deleted.

        Goal: Ensure legacy test files removed from old locations.
        """
        test_root = Path(__file__).parent.parent.parent

        # Check old unit test locations
        old_splunk_test = test_root / "unit" / "connectors" / "test_splunk_connector.py"
        old_openai_test = test_root / "unit" / "connectors" / "test_openai_connector.py"

        assert not old_splunk_test.exists(), (
            "Old Splunk test should be moved to third_party_integrations/"
        )
        assert not old_openai_test.exists(), (
            "Old OpenAI test should be moved to third_party_integrations/"
        )

        # Check old integration test locations
        old_integration_tests = list(test_root.glob("integration/test_splunk_*.py"))
        old_integration_tests += list(test_root.glob("integration/test_openai_*.py"))

        assert len(old_integration_tests) == 0, (
            f"Old integration tests should be moved, found: {old_integration_tests}"
        )
