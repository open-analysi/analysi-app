"""
Integration tests for Splunk framework integration.

End-to-end tests for Splunk integration via Naxos framework.
"""

import pytest

from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
class TestSplunkIntegrationEndToEnd:
    """End-to-end integration tests for Splunk."""

    @pytest.mark.asyncio
    async def test_splunk_discovered_by_registry(self):
        """Test: Registry returns Splunk from manifest scanning.

        Goal: Verify IntegrationRegistryService discovers Splunk via manifest scanning (not static dict).
        """
        registry = IntegrationRegistry()

        # List all integrations
        integrations = registry.list_integrations()

        # Find Splunk
        splunk = next((i for i in integrations if i.id == "splunk"), None)

        assert splunk is not None, "Splunk should be discovered by registry"
        assert splunk.name == "Splunk Enterprise"
        assert len(splunk.actions) >= 10, (
            f"Splunk should have at least 10 actions, got {len(splunk.actions)}"
        )

    @pytest.mark.asyncio
    async def test_splunk_has_siem_archetype(self):
        """Test: Splunk discovered with SIEM archetype."""
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        splunk = next((i for i in integrations if i.id == "splunk"), None)
        assert splunk is not None

        # Should have SIEM archetype
        assert "SIEM" in splunk.archetypes, (
            f"Splunk should have SIEM archetype, got {splunk.archetypes}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestSplunkToolActions:
    """Test specific Splunk tool actions (spl_run, generate_triggering_events_spl)."""

    @pytest.mark.asyncio
    async def test_spl_run_action_exists_in_manifest(self):
        """Test: spl_run action exists in Splunk manifest."""
        registry = IntegrationRegistry()
        splunk = registry.get_integration("splunk")

        assert splunk is not None

        # Find spl_run action
        spl_run = next((a for a in splunk.actions if a.id == "spl_run"), None)

        assert spl_run is not None, "spl_run action should exist in manifest"
        assert "query" in spl_run.categories

        # Check params_schema via metadata property (extra fields)
        params_schema = spl_run.metadata.get("params_schema", {})
        assert "spl_query" in params_schema.get("properties", {})
        assert "timeout" in params_schema.get("properties", {})
        assert "spl_query" in params_schema.get("required", [])

    @pytest.mark.asyncio
    async def test_generate_triggering_events_spl_action_exists_in_manifest(self):
        """Test: generate_triggering_events_spl action exists in Splunk manifest."""
        registry = IntegrationRegistry()
        splunk = registry.get_integration("splunk")

        assert splunk is not None

        # Find generate_triggering_events_spl action
        gen_spl = next(
            (a for a in splunk.actions if a.id == "generate_triggering_events_spl"),
            None,
        )

        assert gen_spl is not None, (
            "generate_triggering_events_spl action should exist in manifest"
        )
        assert "query" in gen_spl.categories

        # Check params_schema via metadata property (extra fields)
        params_schema = gen_spl.metadata.get("params_schema", {})
        assert "alert" in params_schema.get("properties", {})
        assert "lookback_seconds" in params_schema.get("properties", {})
        assert "alert" in params_schema.get("required", [])

    @pytest.mark.requires_splunk
    @pytest.mark.asyncio
    async def test_spl_run_action_execution(self):
        """Test: Execute spl_run action with real Splunk connection using canned search."""
        import os

        from analysi.integrations.framework.loader import IntegrationLoader

        loader = IntegrationLoader()

        # Real Splunk settings - tests run from host, not in Docker
        # So use localhost instead of splunk
        settings = {"host": "localhost", "port": 8089}
        credentials = {
            "username": "admin",
            "password": os.getenv("ANALYSI_SPLUNK_PASSWORD", "changeme123"),
        }
        ctx = {}

        # Load spl_run action
        action = await loader.load_action(
            integration_id="splunk",
            action_id="spl_run",
            action_metadata={"type": "tool"},
            settings=settings,
            credentials=credentials,
            ctx=ctx,
        )

        # Execute action with canned search (generates 1 result without requiring data)
        result = await action.execute(
            spl_query='| makeresults count=1 | eval message="test connectivity"',
            timeout=30,
        )

        # Verify result
        assert result["status"] == "success", f"Expected success, got: {result}"
        assert "events" in result
        assert len(result["events"]) >= 1
        # Verify the generated event contains our test message
        assert any("test connectivity" in str(event) for event in result["events"])

    @pytest.mark.requires_splunk
    @pytest.mark.asyncio
    async def test_spl_run_action_multiple_results(self):
        """Test: Execute spl_run with makeresults generating multiple events."""
        import os

        from analysi.integrations.framework.loader import IntegrationLoader

        loader = IntegrationLoader()

        settings = {"host": "localhost", "port": 8089}
        credentials = {
            "username": "admin",
            "password": os.getenv("ANALYSI_SPLUNK_PASSWORD", "changeme123"),
        }

        action = await loader.load_action(
            integration_id="splunk",
            action_id="spl_run",
            action_metadata={"type": "tool"},
            settings=settings,
            credentials=credentials,
            ctx={},
        )

        # Generate 5 test results
        result = await action.execute(
            spl_query="| makeresults count=5 | streamstats count | eval test_id=count",
            timeout=30,
        )

        assert result["status"] == "success"
        assert "events" in result
        assert len(result["events"]) == 5
        assert result["count"] == 5

    @pytest.mark.requires_splunk
    @pytest.mark.asyncio
    async def test_spl_run_action_with_stats(self):
        """Test: Execute spl_run with stats aggregation (no data required)."""
        import os

        from analysi.integrations.framework.loader import IntegrationLoader

        loader = IntegrationLoader()

        settings = {"host": "localhost", "port": 8089}
        credentials = {
            "username": "admin",
            "password": os.getenv("ANALYSI_SPLUNK_PASSWORD", "changeme123"),
        }

        action = await loader.load_action(
            integration_id="splunk",
            action_id="spl_run",
            action_metadata={"type": "tool"},
            settings=settings,
            credentials=credentials,
            ctx={},
        )

        # Use stats to count results
        result = await action.execute(
            spl_query="| makeresults count=10 | stats count", timeout=30
        )

        assert result["status"] == "success"
        assert "events" in result
        # Stats returns 1 result with count field
        assert len(result["events"]) == 1
        assert "10" in str(result["events"][0])

    @pytest.mark.asyncio
    async def test_generate_triggering_events_spl_action_execution_with_mocked_cim(
        self,
    ):
        """Test: Execute generate_triggering_events_spl action with mocked CIM data."""
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from analysi.integrations.framework.loader import IntegrationLoader

        loader = IntegrationLoader()

        # Settings and credentials (not used for CIM loading, but required by action)
        settings = {"host": "localhost", "port": 8089}
        credentials = {
            "username": "admin",
            "password": os.getenv("ANALYSI_SPLUNK_PASSWORD", "changeme123"),
        }

        # Create mock session
        mock_session = MagicMock()
        ctx = {"session": mock_session, "tenant_id": "test-tenant"}

        # Load action
        action = await loader.load_action(
            integration_id="splunk",
            action_id="generate_triggering_events_spl",
            action_metadata={"type": "tool"},
            settings=settings,
            credentials=credentials,
            ctx=ctx,
        )

        # Mock CIM mappings
        with patch("analysi.data.cim_mappings.CIMMappingLoader") as mock_loader:
            with patch("analysi.utils.splunk_utils.CIMMapper") as mock_mapper:
                with patch("analysi.utils.splunk_utils.SPLGenerator") as mock_generator:
                    # Mock CIM data loader
                    mock_instance = AsyncMock()
                    mock_instance.load_source_to_cim_mappings.return_value = {
                        "Firewall": {
                            "cim_model": "Network_Traffic",
                            "primary_field": "src",
                        }
                    }
                    mock_instance.load_cim_to_sourcetypes_mappings.return_value = {
                        "Network_Traffic": ["pan:traffic", "cisco:asa"]
                    }
                    mock_instance.load_sourcetype_to_index_directory.return_value = {
                        "pan:traffic": {"indexes": ["firewall"]},
                        "cisco:asa": {"indexes": ["firewall"]},
                    }
                    mock_loader.return_value = mock_instance

                    # Mock CIM mapper
                    mock_mapper_instance = MagicMock()
                    mock_mapper.return_value = mock_mapper_instance

                    # Mock SPL generator to return a simple canned search
                    mock_gen_instance = MagicMock()
                    mock_gen_instance.generate_triggering_events_spl.return_value = (
                        "| makeresults count=1 | eval "
                        'src="192.168.1.100", dest="10.0.0.1", action="blocked"'
                    )
                    mock_generator.return_value = mock_gen_instance

                    # Test alert data
                    alert = {
                        "source_category": "Firewall",
                        "triggering_event_time": "2024-01-01T12:00:00Z",
                        "primary_risk_entity": "192.168.1.100",
                        "indicators_of_compromise": ["malicious.com", "bad.exe"],
                    }

                    # Execute action
                    result = await action.execute(alert=alert, lookback_seconds=60)

                    # Verify the action succeeded and returned SPL
                    assert result["status"] == "success", (
                        f"Expected success, got: {result}"
                    )
                    assert "spl_query" in result
                    assert "makeresults" in result["spl_query"]
                    # Verify it includes the primary risk entity
                    assert "192.168.1.100" in result["spl_query"]
