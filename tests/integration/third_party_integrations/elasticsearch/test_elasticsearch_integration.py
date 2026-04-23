"""
Integration tests for Elasticsearch framework integration.

End-to-end tests for Elasticsearch integration via Naxos framework.
Includes registry discovery, manifest validation, and archetype mappings.
"""

import pytest

from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchRegistryDiscovery:
    """Test Elasticsearch is discovered by IntegrationRegistryService."""

    async def test_elasticsearch_discovered_by_registry(self):
        """Test: Registry returns Elasticsearch from manifest scanning."""
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        es = next((i for i in integrations if i.id == "elasticsearch"), None)

        assert es is not None, "Elasticsearch should be discovered by registry"
        assert es.name == "Elasticsearch"
        assert len(es.actions) == 6, (
            f"Elasticsearch should have 6 actions, got {len(es.actions)}"
        )

    async def test_elasticsearch_has_siem_archetype(self):
        """Test: Elasticsearch discovered with SIEM archetype."""
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        es = next((i for i in integrations if i.id == "elasticsearch"), None)
        assert es is not None

        assert "SIEM" in es.archetypes, (
            f"Elasticsearch should have SIEM archetype, got {es.archetypes}"
        )

    async def test_elasticsearch_has_alert_source_archetype(self):
        """Test: Elasticsearch discovered with AlertSource archetype."""
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        es = next((i for i in integrations if i.id == "elasticsearch"), None)
        assert es is not None

        assert "AlertSource" in es.archetypes, (
            f"Elasticsearch should have AlertSource archetype, got {es.archetypes}"
        )

    async def test_elasticsearch_priority(self):
        """Test: Elasticsearch has expected priority."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")

        assert es is not None
        assert es.priority == 75, (
            f"Elasticsearch should have priority 75, got {es.priority}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchArchetypeMappings:
    """Test Elasticsearch SIEM archetype mappings."""

    async def test_siem_archetype_mappings(self):
        """Test: SIEM archetype methods are properly mapped."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")

        assert es is not None
        mappings = es.archetype_mappings.get("SIEM", {})

        assert mappings.get("query_events") == "run_query"
        assert mappings.get("get_alerts") == "run_query"

    async def test_alert_source_archetype_mappings(self):
        """Test: AlertSource archetype methods are properly mapped."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")

        assert es is not None
        mappings = es.archetype_mappings.get("AlertSource", {})

        assert mappings.get("pull_alerts") == "pull_alerts"
        assert mappings.get("alerts_to_ocsf") == "alerts_to_ocsf"


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchActionsRegistered:
    """Test Elasticsearch actions are registered with correct metadata."""

    async def test_health_check_action_metadata(self):
        """Test: health_check action has correct metadata."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        health_check = next((a for a in es.actions if a.id == "health_check"), None)
        assert health_check is not None, "health_check action should exist"
        assert "health_monitoring" in health_check.categories

    async def test_run_query_action_metadata(self):
        """Test: run_query action has correct metadata."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        run_query = next((a for a in es.actions if a.id == "run_query"), None)
        assert run_query is not None, "run_query action should exist"
        assert "query" in run_query.categories

        # Verify params_schema
        params_schema = run_query.metadata.get("params_schema", {})
        assert "index" in params_schema.get("properties", {})
        assert "query" in params_schema.get("properties", {})
        assert "routing" in params_schema.get("properties", {})
        assert "index" in params_schema.get("required", [])

    async def test_index_document_action_metadata(self):
        """Test: index_document action has correct metadata."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        index_doc = next((a for a in es.actions if a.id == "index_document"), None)
        assert index_doc is not None, "index_document action should exist"
        assert "write" in index_doc.categories

        # Verify params_schema
        params_schema = index_doc.metadata.get("params_schema", {})
        assert "index" in params_schema.get("properties", {})
        assert "document" in params_schema.get("properties", {})
        assert "index" in params_schema.get("required", [])
        assert "document" in params_schema.get("required", [])

    async def test_get_config_action_metadata(self):
        """Test: get_config action has correct metadata."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        get_config = next((a for a in es.actions if a.id == "get_config"), None)
        assert get_config is not None, "get_config action should exist"
        assert "discovery" in get_config.categories

    async def test_pull_alerts_action_metadata(self):
        """Test: pull_alerts action has correct metadata."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        pull_alerts = next((a for a in es.actions if a.id == "pull_alerts"), None)
        assert pull_alerts is not None, "pull_alerts action should exist"
        assert "alert_source" in pull_alerts.categories

    async def test_alerts_to_ocsf_action_metadata(self):
        """Test: alerts_to_ocsf action has correct metadata."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        alerts_to_ocsf = next((a for a in es.actions if a.id == "alerts_to_ocsf"), None)
        assert alerts_to_ocsf is not None, "alerts_to_ocsf action should exist"
        assert "normalization" in alerts_to_ocsf.categories

        params_schema = alerts_to_ocsf.metadata.get("params_schema", {})
        assert "raw_alerts" in params_schema.get("required", [])


@pytest.mark.integration
@pytest.mark.asyncio
class TestElasticsearchManifestValidation:
    """Test Elasticsearch manifest is valid and parseable."""

    async def test_manifest_validation(self):
        """Test: Manifest validates successfully."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")

        assert es is not None, "Elasticsearch should load successfully"
        assert es.id == "elasticsearch"
        assert es.name == "Elasticsearch"
        assert es.version == "1.0.0"

    async def test_credential_schema(self):
        """Test: Credential schema has required fields."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        assert es.credential_schema is not None
        props = es.credential_schema.get("properties", {})
        assert "username" in props
        assert "password" in props
        assert props["password"].get("format") == "password"

    async def test_settings_schema(self):
        """Test: Settings schema has required fields."""
        registry = IntegrationRegistry()
        es = registry.get_integration("elasticsearch")
        assert es is not None

        assert es.settings_schema is not None
        props = es.settings_schema.get("properties", {})
        assert "url" in props
        assert "verify_server_cert" in props
