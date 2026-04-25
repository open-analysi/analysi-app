"""Pydantic schemas for Integration system."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator

from analysi.schemas.integration_settings import (
    get_settings_model,
)


# Integration Schemas
class IntegrationCreate(BaseModel):
    """Schema for creating an integration."""

    integration_id: str | None = (
        None  # Human-readable ID like "splunk-prod" (auto-generated if not provided)
    )
    integration_type: str  # Type like "splunk", "echo_edr"
    name: str  # Display name
    description: str | None = None
    enabled: bool = True
    settings: dict[str, Any] | None = None  # Non-secret config

    @model_validator(mode="after")
    def validate_settings(self):
        """Validate settings using the appropriate Pydantic model (if available)."""
        if self.settings:
            from pydantic import ValidationError

            try:
                model_class = get_settings_model(self.integration_type)
                if model_class:
                    # Legacy integration - use hardcoded Pydantic model
                    validated = model_class(**self.settings)
                    self.settings = validated.model_dump(exclude_unset=True)
                # else: Naxos framework integration - uses manifest-based validation
            except (ValueError, ValidationError) as e:
                raise ValueError(f"Invalid settings for {self.integration_type}: {e}")
        return self


class IntegrationUpdate(BaseModel):
    """Schema for updating an integration."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    settings: dict[str, Any] | None = None

    # For validation, we need the integration_type
    _integration_type: str | None = None

    def validate_settings_with_type(self, integration_type: str):
        """Validate settings using the appropriate Pydantic model (if available)."""
        if self.settings:
            from pydantic import ValidationError

            try:
                model_class = get_settings_model(integration_type)
                if model_class:
                    # Legacy integration - use hardcoded Pydantic model
                    validated = model_class(**self.settings)
                    self.settings = validated.model_dump(exclude_unset=True)
                # else: Naxos framework integration - uses manifest-based validation
            except (ValueError, ValidationError) as e:
                raise ValueError(f"Invalid settings for {integration_type}: {e}")


class IntegrationHealth(BaseModel):
    """Schema for integration health status."""

    status: str  # 'healthy', 'degraded', 'unhealthy', 'unknown'
    last_successful_run: datetime | None = None
    recent_failure_rate: float = 0.0
    message: str = ""


class ManagedScheduleSummary(BaseModel):
    """Inline schedule summary within a managed resource."""

    type: str
    value: str
    enabled: bool


class ManagedLastRun(BaseModel):
    """Inline last-run summary within a managed resource."""

    status: str
    at: str | None = None
    task_run_id: str


class ManagedResourceSummary(BaseModel):
    """Schema for a single managed resource returned by GET /managed."""

    resource_key: str
    task_id: str
    task_name: str
    schedule_id: str | None = None
    schedule: ManagedScheduleSummary | None = None
    last_run: ManagedLastRun | None = None
    next_run_at: str | None = None


# Alias for the integration detail response (same shape)
ManagedResourceBlock = ManagedResourceSummary


class ManagedTaskDetail(BaseModel):
    """Schema for GET /managed/{resource_key}/task."""

    task_id: str
    name: str
    description: str | None = None
    script: str | None = None
    function: str | None = None
    scope: str | None = None
    origin_type: str
    integration_id: str | None = None
    created_at: str | None = None


class ManagedScheduleDetail(BaseModel):
    """Schema for GET/PUT /managed/{resource_key}/schedule."""

    schedule_id: str
    schedule_type: str
    schedule_value: str
    enabled: bool
    timezone: str | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None


class ManagedRunItem(BaseModel):
    """Schema for items in GET /managed/{resource_key}/runs."""

    task_run_id: str
    status: str
    run_context: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str


class ManagedAdHocRunResult(BaseModel):
    """Schema for POST /managed/{resource_key}/run response."""

    task_run_id: str
    status: str
    task_id: str
    resource_key: str


# Tool & Registry Responses (Project Sifnos)
class ToolParamsSchema(BaseModel):
    """JSON Schema for tool parameters."""

    type: str = "object"
    properties: dict[str, Any] = {}
    required: list[str] = []


class ToolSummary(BaseModel):
    """Summary of a single tool for autocomplete."""

    fqn: str
    name: str
    description: str = ""
    category: str
    integration_id: str | None = None
    params_schema: ToolParamsSchema


class AllToolsResponse(BaseModel):
    """Response from listing all tools."""

    tools: list[ToolSummary]
    total: int


class IntegrationRegistrySummary(BaseModel):
    """Summary of an integration type from the registry."""

    integration_type: str
    display_name: str
    description: str = ""
    action_count: int
    archetypes: list[str] = []
    priority: int = 0
    integration_id_config: dict[str, Any] | None = None
    requires_credentials: bool = False


class IntegrationActionResponse(BaseModel):
    """Details of a single integration action."""

    action_id: str
    name: str
    description: str = ""
    categories: list[str] = []
    cy_name: str | None = None
    enabled: bool = True
    params_schema: dict[str, Any] = {}
    result_schema: dict[str, Any] = {}


class IntegrationRegistryDetail(BaseModel):
    """Full detail of an integration type from the registry."""

    integration_type: str
    display_name: str
    description: str = ""
    credential_schema: dict[str, Any] = {}
    settings_schema: dict[str, Any] = {}
    integration_id_config: dict[str, Any] | None = None
    requires_credentials: bool = False
    archetypes: list[str] = []
    priority: int = 0
    archetype_mappings: dict[str, Any] | None = None
    actions: list[IntegrationActionResponse] = []


class IntegrationToggleResponse(BaseModel):
    """Response when enabling/disabling an integration."""

    status: str
    integration_id: str


class IntegrationResponse(BaseModel):
    """Schema for integration responses."""

    integration_id: str
    integration_type: str
    tenant_id: str
    name: str
    description: str | None
    enabled: bool
    settings: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    health: IntegrationHealth | None = None
    managed_resources: dict[str, ManagedResourceBlock] | None = None

    model_config = {"from_attributes": True}


class ProvisionFreeIntegrationResult(BaseModel):
    """Result for a single integration in the provision-free response."""

    integration_type: str
    integration_id: str
    name: str
    status: str  # "created" or "already_exists"


class ProvisionFreeResponse(BaseModel):
    """Response from POST /integrations/provision-free."""

    created: int
    already_exists: int
    integrations: list[ProvisionFreeIntegrationResult]
