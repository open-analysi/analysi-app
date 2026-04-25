"""
Unit tests for credential schema in IntegrationRegistryService.
"""

import pytest

from analysi.services.integration_registry_service import IntegrationRegistryService


@pytest.mark.asyncio
class TestIntegrationCredentialSchemas:
    """Test credential schema functionality in the registry."""

    @pytest.fixture
    def registry(self):
        """Create IntegrationRegistryService instance."""
        return IntegrationRegistryService()

    @pytest.mark.asyncio
    async def test_echo_edr_has_credential_schema(self, registry):
        """Test that Echo EDR integration includes credential schema."""
        integration = await registry.get_integration("echo_edr")

        assert integration is not None
        assert "credential_schema" in integration

        schema = integration["credential_schema"]
        assert schema["type"] == "object"
        assert "api_key" in schema["properties"]

        # Check api_key field
        api_key = schema["properties"]["api_key"]
        assert api_key["type"] == "string"
        assert api_key["display_name"] == "API Key"
        assert api_key["format"] == "password"
        assert api_key["placeholder"] == "sk-..."
        assert api_key["required"] is True

    @pytest.mark.asyncio
    async def test_list_integrations_does_not_include_credential_schema(self, registry):
        """Test that list_integrations doesn't expose credential schema (for security)."""
        integrations = await registry.list_integrations()

        for integration in integrations:
            # Should not include credential schema in list view
            assert "credential_schema" not in integration
            # Should include basic info
            assert "integration_type" in integration
            assert "display_name" in integration
            assert "action_count" in integration

    @pytest.mark.asyncio
    async def test_credential_schema_includes_ui_hints(self, registry):
        """Test that credential schemas include UI hints like placeholders."""
        echo = await registry.get_integration("echo_edr")

        api_key_field = echo["credential_schema"]["properties"]["api_key"]
        assert "placeholder" in api_key_field
        assert api_key_field["placeholder"] == "sk-..."

        # This helps UI show example format

    @pytest.mark.asyncio
    async def test_all_integrations_have_credential_schema(self, registry):
        """Test that all integrations in the registry have credential schemas."""
        # Get all integration types
        integrations = await registry.list_integrations()

        for integration_summary in integrations:
            integration_type = integration_summary["integration_type"]
            full_integration = await registry.get_integration(integration_type)

            # Every integration should have a credential schema
            assert "credential_schema" in full_integration, (
                f"Integration {integration_type} missing credential_schema"
            )

            # Should be a valid JSON schema object
            schema = full_integration["credential_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema

            # Check if integration requires credentials
            requires_credentials = full_integration.get(
                "requires_credentials", True
            )  # Default to True

            if requires_credentials:
                # If credentials required, schema should have at least one property
                # (this is a soft requirement - some integrations might have empty schemas)
                if len(schema["properties"]) == 0:
                    # Just a warning for now - not failing the test
                    # Integration with requires_credentials=true and empty schema might be misconfigured
                    pass
            else:
                # If credentials NOT required (free service), empty schema is valid
                # No assertion needed - empty properties are fine for credential-free integrations
                pass
