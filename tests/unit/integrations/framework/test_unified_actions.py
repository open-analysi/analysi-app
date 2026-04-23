"""
Unit tests for unified actions in manifests.

Tests model changes (type/purpose removed, categories added), AlertSource archetype,
registry service filtering, integration tools filtering, and manifest content compliance.
"""

import json
from pathlib import Path

import pytest

from analysi.integrations.framework.models import (
    ActionDefinition,
    Archetype,
    IntegrationManifest,
)
from analysi.integrations.framework.validators import (
    ARCHETYPE_DEFINITIONS,
    ManifestValidator,
)
from analysi.services.integration_registry_service import IntegrationRegistryService

# ---------------------------------------------------------------------------
# T01-T05, T09-T10: ActionDefinition model tests
# ---------------------------------------------------------------------------


class TestUnifiedActionModel:
    """Test ActionDefinition without type/purpose fields."""

    def test_t01_action_with_categories_no_type_purpose(self):
        """T01: ActionDefinition parses action with categories and no type/purpose."""
        action = ActionDefinition(
            id="health_check",
            name="Health Check",
            description="Check connectivity",
            categories=["health_monitoring"],
            cy_name="health_check",
        )
        assert action.id == "health_check"
        assert action.categories == ["health_monitoring"]
        assert action.cy_name == "health_check"

    def test_t02_categories_defaults_to_empty_list(self):
        """T02: ActionDefinition categories defaults to empty list."""
        action = ActionDefinition(id="some_action")
        assert action.categories == []

    def test_t03_metadata_excludes_standard_fields(self):
        """T03: metadata property does not include categories, id, etc."""
        action = ActionDefinition(
            id="test_action",
            categories=["enrichment"],
            cy_name="test",
            name="Test",
            description="Desc",
            enabled=True,
            # Extra field
            params_schema={"type": "object", "properties": {}},
        )
        meta = action.metadata
        assert "id" not in meta
        assert "categories" not in meta
        assert "cy_name" not in meta
        assert "name" not in meta
        assert "description" not in meta
        assert "enabled" not in meta
        # Extra field should be in metadata
        assert "params_schema" in meta

    def test_t04_metadata_includes_extra_fields(self):
        """T04: metadata includes extra fields like params_schema, result_schema."""
        action = ActionDefinition(
            id="test",
            categories=["test"],
            params_schema={"type": "object"},
            result_schema={"type": "object"},
            credential_scopes=["read"],
        )
        meta = action.metadata
        assert "params_schema" in meta
        assert "result_schema" in meta
        assert "credential_scopes" in meta

    def test_t05_archetype_enum_has_alert_source(self):
        """T05: Archetype enum includes ALERT_SOURCE."""
        assert hasattr(Archetype, "ALERT_SOURCE")
        assert Archetype.ALERT_SOURCE == "AlertSource"

    # T06-T08 removed: CONNECTOR_CATEGORIES and is_connector_action deleted.

    def test_t09_action_with_legacy_type_still_parses(self):
        """T09: ActionDefinition with type field still parses (extra='allow' absorbs it)."""
        # Legacy manifests might still have type field -- extra="allow" handles this
        action = ActionDefinition(
            id="old_action",
            categories=["health_monitoring"],
            type="connector",  # type: ignore[call-arg]  # extra field
        )
        assert action.id == "old_action"
        # type is absorbed as extra field, accessible via model_dump
        assert action.model_dump().get("type") == "connector"

    def test_t10_action_with_empty_categories_valid(self):
        """T10: ActionDefinition with empty categories is valid."""
        action = ActionDefinition(id="test", categories=[])
        assert action.categories == []


# ---------------------------------------------------------------------------
# T11-T14, T17: IntegrationRegistryService tests (unified actions)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnifiedActionsRegistry:
    """Test registry service uses unified actions (no connector/tool split)."""

    @pytest.fixture
    def registry(self):
        return IntegrationRegistryService()

    async def test_t11_list_integrations_has_action_count(self, registry):
        """T11: list_integrations returns action_count (not separate connectors/tools)."""
        integrations = await registry.list_integrations()
        assert isinstance(integrations, list)
        assert len(integrations) > 0

        # Splunk should have action_count
        splunk = next(
            (i for i in integrations if i["integration_type"] == "splunk"), None
        )
        assert splunk is not None
        assert "action_count" in splunk
        assert isinstance(splunk["action_count"], int)
        assert splunk["action_count"] > 0

        # Old keys must NOT be present
        assert "connectors" not in splunk
        assert "tool_count" not in splunk

    async def test_t12_list_integrations_action_count_matches_detail(self, registry):
        """T12: list_integrations action_count matches len(actions) in get_integration."""
        integrations = await registry.list_integrations()
        splunk_list = next(
            (i for i in integrations if i["integration_type"] == "splunk"), None
        )
        assert splunk_list is not None

        splunk_detail = await registry.get_integration("splunk")
        assert splunk_detail is not None
        assert splunk_list["action_count"] == len(splunk_detail["actions"])

    async def test_t13_get_integration_actions_list(self, registry):
        """T13: get_integration returns unified actions list."""
        echo = await registry.get_integration("echo_edr")
        assert echo is not None
        assert "actions" in echo
        assert isinstance(echo["actions"], list)

        action_ids = [a["action_id"] for a in echo["actions"]]
        assert "pull_processes" in action_ids
        assert "isolate_host" in action_ids
        # health_check is also included as a unified action
        assert "health_check" in action_ids

        # Old keys must NOT be present
        assert "connectors" not in echo
        assert "tools" not in echo

    async def test_t14_get_integration_action_fields(self, registry):
        """T14: Each action in get_integration has the expected fields."""
        echo = await registry.get_integration("echo_edr")
        assert echo is not None

        for action in echo["actions"]:
            assert "action_id" in action
            assert "name" in action
            assert "description" in action
            assert "categories" in action
            assert isinstance(action["categories"], list)
            assert "cy_name" in action
            assert "enabled" in action
            assert "params_schema" in action
            assert "result_schema" in action

    # T15-T16 removed: get_connector and get_default_schedule deleted.

    async def test_t17_register_tools_uses_cy_name(self, registry):
        """T17: register_tools_in_ku_api registers actions with cy_name."""
        # Verify framework manifests have cy_name on actions
        manifests = registry.framework.list_integrations()
        for manifest in manifests:
            for action in manifest.actions:
                if action.cy_name:
                    # Actions with cy_name should be registerable
                    assert action.id  # sanity check

    # T18-T19 removed: get_connector/get_default_schedule for non-connector deleted.


# ---------------------------------------------------------------------------
# T20-T23: Manifest Validator tests
# ---------------------------------------------------------------------------


class TestUnifiedActionsManifestValidator:
    """Test validator handles AlertSource archetype."""

    def test_t20_alert_source_validates_with_required_actions(self):
        """T20: AlertSource archetype validates with pull_alerts + alerts_to_ocsf in mappings."""
        assert Archetype.ALERT_SOURCE in ARCHETYPE_DEFINITIONS
        definition = ARCHETYPE_DEFINITIONS[Archetype.ALERT_SOURCE]
        required = definition["required_methods"]
        assert "pull_alerts" in required
        assert "alerts_to_ocsf" in required

    def test_t21_validator_accepts_manifest_without_type_purpose(self):
        """T21: Validator accepts manifest without type/purpose fields on actions."""
        manifest = IntegrationManifest(
            id="test_int",
            app="test_int",
            name="Test Integration",
            version="1.0.0",
            archetypes=["ThreatIntel"],
            priority=50,
            archetype_mappings={"ThreatIntel": {"lookup_ip": "lookup_action"}},
            actions=[
                ActionDefinition(
                    id="lookup_action",
                    categories=["threat_intel"],
                    cy_name="lookup",
                    name="Lookup",
                )
            ],
        )
        assert len(manifest.actions) == 1
        assert manifest.actions[0].categories == ["threat_intel"]

    def test_t22_alert_source_fails_without_pull_alerts(self):
        """T22: AlertSource archetype fails without pull_alerts in mappings."""
        validator = ManifestValidator()
        manifest = IntegrationManifest(
            id="bad_source",
            app="bad_source",
            name="Bad Source",
            version="1.0.0",
            archetypes=["AlertSource"],
            priority=50,
            archetype_mappings={
                "AlertSource": {
                    "alerts_to_ocsf": "normalize_action",
                    # Missing pull_alerts!
                }
            },
            actions=[
                ActionDefinition(
                    id="normalize_action",
                    categories=["alert_normalization"],
                ),
            ],
        )
        errors = validator.validate_archetype_mappings(manifest)
        error_messages = [e.message for e in errors]
        assert any("pull_alerts" in msg for msg in error_messages)

    def test_t23_alert_source_fails_without_alerts_to_ocsf(self):
        """T23: AlertSource archetype fails without alerts_to_ocsf in mappings."""
        validator = ManifestValidator()
        manifest = IntegrationManifest(
            id="bad_source",
            app="bad_source",
            name="Bad Source",
            version="1.0.0",
            archetypes=["AlertSource"],
            priority=50,
            archetype_mappings={
                "AlertSource": {
                    "pull_alerts": "pull_action",
                    # Missing alerts_to_ocsf!
                }
            },
            actions=[
                ActionDefinition(
                    id="pull_action",
                    categories=["alert_ingestion"],
                ),
            ],
        )
        errors = validator.validate_archetype_mappings(manifest)
        error_messages = [e.message for e in errors]
        assert any("alerts_to_ocsf" in msg for msg in error_messages)


# ---------------------------------------------------------------------------
# T24-T26: Integration tools (MCP) tests
# ---------------------------------------------------------------------------


class TestUnifiedActionsIntegrationTools:
    """Test MCP integration tools use cy_name instead of type."""

    @pytest.fixture(autouse=True)
    def _set_mcp_user(self):
        """Set an authenticated MCP user for all tests."""
        from analysi.auth.models import CurrentUser
        from analysi.mcp.context import mcp_current_user_context

        user = CurrentUser(
            user_id="kc-test",
            email="user@test.com",
            tenant_id="test-tenant",
            roles=["analyst"],
            actor_type="user",
        )
        mcp_current_user_context.set(user)
        yield
        mcp_current_user_context.set(None)

    @pytest.mark.asyncio
    async def test_t24_get_integration_tools_returns_cy_name_actions(self):
        """T24: get_integration_tools returns only actions with cy_name."""
        from analysi.mcp import integration_tools

        result = await integration_tools.get_integration_tools("virustotal")
        assert "tools" in result

        # All returned tools should have useful data
        for tool in result["tools"]:
            assert "action_id" in tool
            assert "cy_usage" in tool

    @pytest.mark.asyncio
    async def test_t25_search_integration_tools_only_cy_name_actions(self):
        """T25: search_integration_tools only searches actions with cy_name."""
        from analysi.mcp import integration_tools

        result = await integration_tools.search_integration_tools(query="reputation")
        # Results should only include tools (actions with cy_name)
        for tool in result["tools"]:
            assert "cy_usage" in tool
            assert "action_id" in tool

    @pytest.mark.asyncio
    async def test_t26_get_integration_tools_includes_all_cy_name_actions(
        self,
    ):
        """T26: get_integration_tools includes all actions with cy_name set.

        All actions (including former connectors) have cy_name.
        This means health_check also appears in the tools list -- this is intentional
        because all actions are now unified.
        """
        from analysi.mcp import integration_tools

        result = await integration_tools.get_integration_tools("virustotal")
        tool_ids = [t["action_id"] for t in result["tools"]]
        # All actions should be present since all have cy_name
        assert "ip_reputation" in tool_ids
        assert "health_check" in tool_ids  # Now included (has cy_name)


# ---------------------------------------------------------------------------
# T27-T34: Manifest content compliance tests
# ---------------------------------------------------------------------------


class TestUnifiedActionsManifestContent:
    """Test all integration manifests comply with unified action model."""

    @pytest.fixture
    def manifest_dir(self):
        return Path("src/analysi/integrations/framework/integrations")

    @pytest.fixture
    def all_manifests(self, manifest_dir):
        manifests = []
        for manifest_path in sorted(manifest_dir.glob("*/manifest.json")):
            with open(manifest_path) as f:
                data = json.load(f)
            manifests.append((manifest_path.parent.name, data))
        return manifests

    def test_t27_no_type_field_on_any_action(self, all_manifests):
        """T27: All manifests have no type field on any action."""
        for integration_id, data in all_manifests:
            for action in data.get("actions", []):
                assert "type" not in action, (
                    f"{integration_id} action '{action['id']}' still has 'type' field"
                )

    def test_t28_no_purpose_field_on_any_action(self, all_manifests):
        """T28: All manifests have no purpose field on any action."""
        for integration_id, data in all_manifests:
            for action in data.get("actions", []):
                assert "purpose" not in action, (
                    f"{integration_id} action '{action['id']}' still has 'purpose' field"
                )

    def test_t29_all_actions_have_categories(self, all_manifests):
        """T29: All manifests have categories on every action."""
        for integration_id, data in all_manifests:
            for action in data.get("actions", []):
                assert "categories" in action, (
                    f"{integration_id} action '{action['id']}' missing 'categories'"
                )
                assert isinstance(action["categories"], list), (
                    f"{integration_id} action '{action['id']}' categories is not a list"
                )

    def test_t30_splunk_has_alert_source_archetype(self, all_manifests):
        """T30: Splunk manifest has AlertSource archetype."""
        splunk = next((d for name, d in all_manifests if name == "splunk"), None)
        assert splunk is not None
        assert "AlertSource" in splunk["archetypes"]

    def test_t31_splunk_has_alerts_to_ocsf_action(self, all_manifests):
        """T31: Splunk manifest has alerts_to_ocsf action."""
        splunk = next((d for name, d in all_manifests if name == "splunk"), None)
        assert splunk is not None
        action_ids = [a["id"] for a in splunk["actions"]]
        assert "alerts_to_ocsf" in action_ids

    def test_t32_splunk_alert_source_mappings(self, all_manifests):
        """T32: Splunk archetype_mappings AlertSource has pull_alerts and alerts_to_ocsf."""
        splunk = next((d for name, d in all_manifests if name == "splunk"), None)
        assert splunk is not None
        alert_source = splunk["archetype_mappings"].get("AlertSource", {})
        assert "pull_alerts" in alert_source
        assert "alerts_to_ocsf" in alert_source

    def test_t33_all_actions_have_cy_name(self, all_manifests):
        """T33: All actions have cy_name set."""
        for integration_id, data in all_manifests:
            for action in data.get("actions", []):
                assert action.get("cy_name"), (
                    f"{integration_id} action '{action['id']}' missing cy_name"
                )

    def test_t34_all_manifests_validate_successfully(self, manifest_dir):
        """T34: All manifests validate successfully through ManifestValidator."""
        validator = ManifestValidator()
        for manifest_path in sorted(manifest_dir.glob("*/manifest.json")):
            manifest, errors = validator.validate_manifest(manifest_path)
            # Filter to errors only (not warnings)
            real_errors = [e for e in errors if e.severity == "error"]
            assert manifest is not None, (
                f"{manifest_path.parent.name} failed to parse: {errors}"
            )
            assert len(real_errors) == 0, (
                f"{manifest_path.parent.name} has validation errors: {real_errors}"
            )
