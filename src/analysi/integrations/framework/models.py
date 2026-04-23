"""
Data models for Integrations Framework.

Pydantic models for manifest validation and API responses.
All actions use `categories` for classification.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Archetype(StrEnum):
    """Known integration archetypes."""

    AI = "AI"
    SIEM = "SIEM"
    EDR = "EDR"
    SOAR = "SOAR"
    THREAT_INTEL = "ThreatIntel"
    TICKETING_SYSTEM = "TicketingSystem"
    COMMUNICATION = "Communication"
    NOTIFICATION = "Notification"
    CLOUD_PROVIDER = "CloudProvider"
    NETWORK_SECURITY = "NetworkSecurity"
    IDENTITY_PROVIDER = "IdentityProvider"
    VULNERABILITY_MANAGEMENT = "VulnerabilityManagement"
    SANDBOX = "Sandbox"
    EMAIL_SECURITY = "EmailSecurity"
    CLOUD_STORAGE = "CloudStorage"
    DATABASE_ENRICHMENT = "DatabaseEnrichment"
    FORENSICS_TOOLS = "ForensicsTools"
    GEOLOCATION = "Geolocation"
    LAKEHOUSE = "Lakehouse"
    DNS = "DNS"
    AGENTIC_FRAMEWORK = "AgenticFramework"
    ALERT_SOURCE = "AlertSource"


class ActionDefinition(BaseModel):
    """Definition of an integration action from manifest.

    All actions are classified by ``categories``.  Manifests that carry
    ``type``/``purpose`` will parse without error because the model uses
    ``extra="allow"``, but those fields are ignored by the application.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Action identifier")
    name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Action description")
    categories: list[str] = Field(
        default_factory=list,
        description="Action categories for discovery and filtering",
    )
    cy_name: str | None = Field(None, description="Cy-callable tool name (FQN)")
    enabled: bool = Field(True, description="Whether action is enabled")

    @property
    def metadata(self) -> dict[str, Any]:
        """
        Get extra metadata fields from manifest.

        Includes: credential_scopes, default_schedule, params_schema, result_schema
        """
        # Get all extra fields (not defined in model)
        standard_fields = {
            "id",
            "name",
            "description",
            "categories",
            "cy_name",
            "enabled",
        }
        return {k: v for k, v in self.model_dump().items() if k not in standard_fields}


class CredentialConfig(BaseModel):
    """Credential configuration from manifest."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Credential type (api_key, basic_auth, etc.)")
    fields: list[str] = Field(..., description="Required credential fields")


class IntegrationManifest(BaseModel):
    """Integration manifest loaded from manifest.json."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Integration identifier")
    app: str = Field(..., description="App name")
    name: str = Field(..., description="Display name")
    version: str = Field(..., description="Version string")
    description: str | None = Field(None, description="Integration description")
    archetypes: list[str] = Field(..., description="Archetype types implemented")
    priority: int = Field(
        ..., ge=1, le=100, description="Priority for archetype routing (1-100)"
    )
    archetype_mappings: dict[str, dict[str, str]] = Field(
        ..., description="Maps archetype methods to action IDs"
    )
    actions: list[ActionDefinition] = Field(..., description="Action definitions")
    credentials: CredentialConfig | None = Field(None, description="Credential config")
    requires_credentials: bool = Field(
        True,
        description="Whether this integration requires credentials to function. "
        "Defaults to True (fail-safe). Set to False for free/public services that don't need authentication.",
    )

    @property
    def credential_schema(self) -> dict[str, Any] | None:
        """Get credential_schema from extra fields."""
        return self.model_dump().get("credential_schema")

    @property
    def settings_schema(self) -> dict[str, Any] | None:
        """Get settings_schema from extra fields."""
        return self.model_dump().get("settings_schema")

    @property
    def integration_id_config(self) -> dict[str, Any] | None:
        """Get integration_id_config from extra fields."""
        return self.model_dump().get("integration_id_config")


class ValidationError(BaseModel):
    """Validation error from manifest validator."""

    field: str = Field(..., description="Field with error")
    message: str = Field(..., description="Error message")
    severity: Literal["error", "warning"] = Field("error", description="Severity level")
