"""
Per-integration credential schemas for type-safe credential handling.
"""

from pydantic import BaseModel, Field


class BaseIntegrationCredential(BaseModel):
    """Base class for all integration credentials."""

    class Config:
        extra = "forbid"  # Prevent extra fields


class SplunkCredential(BaseIntegrationCredential):
    """Splunk authentication credentials."""

    username: str = Field(..., description="Splunk username")
    password: str = Field(..., description="Splunk password")
    host: str = Field(..., description="Splunk host (without protocol)")
    port: int = Field(default=8089, description="Splunk management port")


class EchoEDRCredential(BaseIntegrationCredential):
    """Echo EDR authentication credentials (mock integration)."""

    api_key: str = Field(..., description="Echo EDR API key")
    base_url: str = Field(..., description="Echo EDR API base URL")


# Registry mapping integration types to credential schemas
CREDENTIAL_SCHEMAS = {
    "splunk": SplunkCredential,
    "echo_edr": EchoEDRCredential,
}


def get_credential_schema(integration_type: str):
    """Get the credential schema for a specific integration type."""
    if integration_type not in CREDENTIAL_SCHEMAS:
        raise KeyError(
            f"No credential schema defined for integration type: {integration_type}"
        )
    return CREDENTIAL_SCHEMAS[integration_type]


def validate_credentials(
    integration_type: str, credentials: dict
) -> BaseIntegrationCredential:
    """Validate and parse credentials for a specific integration type."""
    schema_class = get_credential_schema(integration_type)
    return schema_class(**credentials)
