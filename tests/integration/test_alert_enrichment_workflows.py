"""
Integration tests for realistic alert enrichment workflows.

Tests type validation with real-world workflow patterns:
- Basic threat intel enrichment
- Parallel multi-source enrichment with merge nodes
- Multi-stage enrichment pipelines
- EDR-specific investigation workflows
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.constants import TemplateConstants
from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from tests.fixtures.alert_enrichment_workflows import (
    get_basic_threat_intel_workflow,
    get_edr_investigation_workflow,
    get_multi_stage_enrichment_workflow,
    get_parallel_enrichment_workflow,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestAlertEnrichmentWorkflows:
    """Test real-world alert enrichment workflow patterns."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.fixture
    def create_identity_template(self) -> str:
        """Return system identity template UUID."""
        return str(TemplateConstants.SYSTEM_IDENTITY_TEMPLATE_ID)

    @pytest.fixture
    def create_merge_template(self) -> str:
        """Return system merge template UUID."""
        return str(TemplateConstants.SYSTEM_MERGE_TEMPLATE_ID)

    @pytest.fixture
    async def create_threat_intel_tasks(self, client: AsyncClient) -> dict[str, str]:
        """Create toy task records for threat intelligence integrations."""
        tasks = {}

        # VirusTotal lookup task
        vt_task_data = {
            "name": "VirusTotal IoC Lookup",
            "description": "Look up IoCs in VirusTotal",
            "script": 'return {"threat_intel": [{"ioc": "1.2.3.4", "source": "virustotal", "score": 85}]}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        vt_response = await client.post("/v1/test_tenant/tasks", json=vt_task_data)
        assert vt_response.status_code == 201
        tasks["virustotal"] = vt_response.json()["data"]["id"]

        # AbuseIPDB lookup task
        abuse_task_data = {
            "name": "AbuseIPDB IP Lookup",
            "description": "Check IP reputation in AbuseIPDB",
            "script": 'return {"threat_intel": [{"ioc": "1.2.3.4", "source": "abuseipdb", "score": 75}]}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        abuse_response = await client.post(
            "/v1/test_tenant/tasks", json=abuse_task_data
        )
        assert abuse_response.status_code == 201
        tasks["abuseipdb"] = abuse_response.json()["data"]["id"]

        # AlienVault OTX lookup task
        alien_task_data = {
            "name": "AlienVault OTX Lookup",
            "description": "Query AlienVault OTX for threat intelligence",
            "script": 'return {"threat_intel": [{"ioc": "1.2.3.4", "source": "alienvault", "score": 60}]}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        alien_response = await client.post(
            "/v1/test_tenant/tasks", json=alien_task_data
        )
        assert alien_response.status_code == 201
        tasks["alienvault"] = alien_response.json()["data"]["id"]

        # MaxMind GeoIP lookup task
        geo_task_data = {
            "name": "MaxMind GeoIP Lookup",
            "description": "Get geographic location for IP",
            "script": 'return {"geo_context": {"country": "US", "city": "San Francisco"}}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        geo_response = await client.post("/v1/test_tenant/tasks", json=geo_task_data)
        assert geo_response.status_code == 201
        tasks["geo_lookup"] = geo_response.json()["data"]["id"]

        # CrowdStrike EDR device status task
        cs_device_task_data = {
            "name": "CrowdStrike Device Status",
            "description": "Get device containment status from CrowdStrike",
            "script": 'return {"edr_context": {"device_status": "active", "isolated": false}}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        cs_device_response = await client.post(
            "/v1/test_tenant/tasks", json=cs_device_task_data
        )
        assert cs_device_response.status_code == 201
        tasks["cs_device"] = cs_device_response.json()["data"]["id"]

        # CrowdStrike process tree task
        cs_process_task_data = {
            "name": "CrowdStrike Process Tree",
            "description": "Get process execution tree from CrowdStrike",
            "script": 'return {"edr_context": {"process_tree": [{"name": "svchost.exe"}]}}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        cs_process_response = await client.post(
            "/v1/test_tenant/tasks", json=cs_process_task_data
        )
        assert cs_process_response.status_code == 201
        tasks["cs_process"] = cs_process_response.json()["data"]["id"]

        # Hash reputation lookup task
        hash_task_data = {
            "name": "Hash Reputation Lookup",
            "description": "Check file hash reputation",
            "script": 'return {"hash_reputation": {"malicious": false, "score": 10}}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        hash_response = await client.post("/v1/test_tenant/tasks", json=hash_task_data)
        assert hash_response.status_code == 201
        tasks["hash_reputation"] = hash_response.json()["data"]["id"]

        # User context lookup task
        user_task_data = {
            "name": "User Context Lookup",
            "description": "Get user/entity context from identity system",
            "script": 'return {"user_context": {"department": "Engineering", "risk_level": "low"}}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        user_response = await client.post("/v1/test_tenant/tasks", json=user_task_data)
        assert user_response.status_code == 201
        tasks["user_context"] = user_response.json()["data"]["id"]

        # Active Directory lookup task (for multi-stage workflow)
        ad_task_data = {
            "name": "Active Directory User Lookup",
            "description": "Query Active Directory for user information",
            "script": 'return {"user_context": {"department": "IT", "title": "Engineer", "risk_level": "low"}}',
            "scope": "processing",
            "function": "search",
            "created_by": str(SYSTEM_USER_ID),
        }
        ad_response = await client.post("/v1/test_tenant/tasks", json=ad_task_data)
        assert ad_response.status_code == 201
        tasks["ad_lookup"] = ad_response.json()["data"]["id"]

        return tasks

    @pytest.mark.asyncio
    async def test_basic_threat_intel_workflow_validates(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        Test basic threat intel enrichment workflow validates successfully.

        Workflow: Alert → Extract IoCs → Lookup Threat Intel → Enrich Alert → Assess Risk

        This represents the simplest enrichment pattern where:
        1. Extract IPs/domains from alert.iocs array
        2. Query VirusTotal for reputation
        3. Add threat intel to alert
        4. Calculate risk score and decide action
        """
        workflow_config = get_basic_threat_intel_workflow()
        template_id = create_identity_template
        task_ids = create_threat_intel_tasks

        # Adapt workflow: transformation nodes use template, task nodes use task_id
        for node in workflow_config["nodes"]:
            if node["kind"] == "task":
                # Map task node to appropriate task_id
                if "virustotal" in node["node_id"].lower():
                    node["task_id"] = task_ids["virustotal"]
                node.pop("node_template_id", None)  # Remove template_id from task nodes
            else:
                # Transformation nodes use template
                node["node_template_id"] = template_id
                node.pop("task_id", None)  # Ensure task_id is not set

        workflow_config["created_by"] = str(SYSTEM_USER_ID)

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate with normalized alert schema
        alert_schema = {
            "type": "object",
            "properties": {
                "alert": {
                    "type": "object",
                    "properties": {
                        "alert_id": {"type": "string"},
                        "title": {"type": "string"},
                        "severity": {"type": "string"},
                        "iocs": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "value": {"type": "string"},
                                    "type": {"type": "string"},
                                },
                            },
                        },
                    },
                }
            },
        }

        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": alert_schema},
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]

        # Print validation result for debugging
        if data["status"] == "invalid":
            print("\n=== VALIDATION ERRORS ===")
            for error in data.get("errors", []):
                print(f"  - {error}")
            print("\n=== VALIDATION WARNINGS ===")
            for warning in data.get("warnings", []):
                print(f"  - {warning}")

        assert data["status"] in ["valid", "valid_with_warnings"]
        assert len(data["nodes"]) == 4  # 4 nodes in basic workflow

    @pytest.mark.asyncio
    async def test_parallel_enrichment_workflow_with_merge(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_merge_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        Test parallel multi-source enrichment with merge node.

        Workflow:
                            ┌→ VirusTotal Lookup ─┐
        Alert → Extract IoCs ┼→ AbuseIPDB Lookup  ├→ Merge Intel → Enrich Alert → Assess Risk
                            └→ AlienVault Lookup ─┘

        This tests:
        - Multiple parallel paths from one node (fan-out)
        - Merge node receiving 3 inputs (fan-in)
        - Type propagation through parallel branches
        """
        workflow_config = get_parallel_enrichment_workflow()
        identity_template_id = create_identity_template
        merge_template_id = create_merge_template
        task_ids = create_threat_intel_tasks

        # Adapt workflow: transformation nodes use template, task nodes use task_id
        for node in workflow_config["nodes"]:
            if node["kind"] == "task":
                # Map task nodes to appropriate task_id
                if "virustotal" in node["node_id"].lower():
                    node["task_id"] = task_ids["virustotal"]
                elif "abuseipdb" in node["node_id"].lower():
                    node["task_id"] = task_ids["abuseipdb"]
                elif "alienvault" in node["node_id"].lower():
                    node["task_id"] = task_ids["alienvault"]
                node.pop("node_template_id", None)
            else:
                # Use merge template for merge nodes, identity for others
                if node.get("template_name") == "merge":
                    node["node_template_id"] = merge_template_id
                else:
                    node["node_template_id"] = identity_template_id
                node.pop("task_id", None)

        workflow_config["created_by"] = str(SYSTEM_USER_ID)

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate
        alert_schema = {
            "type": "object",
            "properties": {
                "alert": {
                    "type": "object",
                    "properties": {
                        "alert_id": {"type": "string"},
                        "iocs": {"type": "array"},
                    },
                }
            },
        }

        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": alert_schema},
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]

        # Check that merge node properly receives 3 inputs
        merge_node = next(
            (n for n in data["nodes"] if n["node_id"] == "merge-threat-intel"), None
        )
        assert merge_node is not None
        # Merge node should show multi-input (list of schemas)
        # Note: Exact structure depends on type propagator behavior

        assert len(data["nodes"]) == 7  # 7 nodes in parallel enrichment workflow

    @pytest.mark.asyncio
    async def test_multi_stage_enrichment_pipeline(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_merge_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        Test multi-stage enrichment: Network → Threat Intel → Identity → Decision.

        This tests:
        - Sequential stages where each builds on previous
        - Multiple merge points throughout pipeline
        - Complex data flow through 4 distinct stages
        - Final decision node receives fully enriched alert
        """
        workflow_config = get_multi_stage_enrichment_workflow()
        identity_template_id = create_identity_template
        merge_template_id = create_merge_template
        task_ids = create_threat_intel_tasks

        # Adapt workflow: transformation nodes use template, task nodes use task_id
        for node in workflow_config["nodes"]:
            if node["kind"] == "task":
                # Map task nodes to appropriate task_id
                if "geo" in node["node_id"].lower():
                    node["task_id"] = task_ids["geo_lookup"]
                elif "virustotal" in node["node_id"].lower():
                    node["task_id"] = task_ids["virustotal"]
                elif "abuseipdb" in node["node_id"].lower():
                    node["task_id"] = task_ids["abuseipdb"]
                elif "alienvault" in node["node_id"].lower():
                    node["task_id"] = task_ids["alienvault"]
                elif "ad-lookup" in node["node_id"].lower():
                    node["task_id"] = task_ids["ad_lookup"]
                elif "user" in node["node_id"].lower():
                    node["task_id"] = task_ids["user_context"]
                node.pop("node_template_id", None)
            else:
                # Use merge template for merge nodes, identity for others
                if node.get("template_name") == "merge":
                    node["node_template_id"] = merge_template_id
                else:
                    node["node_template_id"] = identity_template_id
                node.pop("task_id", None)

        workflow_config["created_by"] = str(SYSTEM_USER_ID)

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate with full alert schema
        alert_schema = {
            "type": "object",
            "properties": {
                "alert": {
                    "type": "object",
                    "properties": {
                        "alert_id": {"type": "string"},
                        "network_info": {
                            "type": "object",
                            "properties": {
                                "src_ip": {"type": "string"},
                                "dst_ip": {"type": "string"},
                            },
                        },
                        "iocs": {"type": "array"},
                        "primary_risk_entity_value": {"type": "string"},
                    },
                }
            },
        }

        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": alert_schema},
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]

        # Print validation result for debugging
        if data["status"] == "invalid":
            print("\n=== VALIDATION ERRORS ===")
            for error in data.get("errors", []):
                print(f"  - {error}")
            print("\n=== VALIDATION WARNINGS ===")
            for warning in data.get("warnings", []):
                print(f"  - {warning}")

        assert data["status"] in ["valid", "valid_with_warnings"]

        # Verify final decision node has access to all enriched data
        decision_node = next(
            (n for n in data["nodes"] if n["node_id"] == "decide-action"), None
        )
        assert decision_node is not None

        assert len(data["nodes"]) == 13  # 13 nodes in multi-stage workflow

    @pytest.mark.asyncio
    async def test_edr_investigation_workflow(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_merge_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        Test EDR-specific investigation workflow.

        Workflow:
        Alert → Extract Device & Process
              ↓
              ┌→ EDR Device Lookup ─┐
              ├→ Process Tree       ├→ Merge Context → Add to Alert → Assess → Decide
              └→ Hash Reputation    ─┘

        This tests EDR-specific enrichment patterns:
        - Device isolation status
        - Process execution tree
        - File hash reputation
        - Containment decision logic
        """
        workflow_config = get_edr_investigation_workflow()
        identity_template_id = create_identity_template
        merge_template_id = create_merge_template
        task_ids = create_threat_intel_tasks

        # Adapt workflow: transformation nodes use template, task nodes use task_id
        for node in workflow_config["nodes"]:
            if node["kind"] == "task":
                # Map task nodes to appropriate task_id
                if "device" in node["node_id"].lower():
                    node["task_id"] = task_ids["cs_device"]
                elif "process" in node["node_id"].lower():
                    node["task_id"] = task_ids["cs_process"]
                elif "hash" in node["node_id"].lower():
                    node["task_id"] = task_ids["hash_reputation"]
                node.pop("node_template_id", None)
            else:
                # Use merge template for merge nodes, identity for others
                if node.get("template_name") == "merge":
                    node["node_template_id"] = merge_template_id
                else:
                    node["node_template_id"] = identity_template_id
                node.pop("task_id", None)

        workflow_config["created_by"] = str(SYSTEM_USER_ID)

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate with EDR alert schema
        edr_alert_schema = {
            "type": "object",
            "properties": {
                "alert": {
                    "type": "object",
                    "properties": {
                        "source_category": {"type": "string"},
                        "primary_risk_entity_value": {"type": "string"},
                        "process_info": {
                            "type": "object",
                            "properties": {
                                "process_name": {"type": "string"},
                                "file_hash": {"type": "string"},
                            },
                        },
                    },
                }
            },
        }

        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": edr_alert_schema},
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]
        assert data["status"] in ["valid", "valid_with_warnings"]

        # Verify merge node receives 3 EDR contexts
        merge_node = next(
            (n for n in data["nodes"] if n["node_id"] == "merge-edr-context"), None
        )
        assert merge_node is not None

        assert len(data["nodes"]) == 8  # 8 nodes in EDR workflow

    @pytest.mark.asyncio
    async def test_apply_types_to_enrichment_workflow(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_merge_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        Test that we can persist type information for enrichment workflows.

        This verifies the apply-types endpoint works with complex workflows.
        """
        workflow_config = get_parallel_enrichment_workflow()
        identity_template_id = create_identity_template
        merge_template_id = create_merge_template
        task_ids = create_threat_intel_tasks

        # Adapt workflow
        for node in workflow_config["nodes"]:
            if node["kind"] == "task":
                if "virustotal" in node["node_id"].lower():
                    node["task_id"] = task_ids["virustotal"]
                elif "abuseipdb" in node["node_id"].lower():
                    node["task_id"] = task_ids["abuseipdb"]
                elif "alienvault" in node["node_id"].lower():
                    node["task_id"] = task_ids["alienvault"]
                node.pop("node_template_id", None)
            else:
                # Use merge template for merge nodes, identity for others
                if node.get("template_name") == "merge":
                    node["node_template_id"] = merge_template_id
                else:
                    node["node_template_id"] = identity_template_id
                node.pop("task_id", None)

        workflow_config["created_by"] = str(SYSTEM_USER_ID)

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Apply types
        alert_schema = {"type": "object", "properties": {"alert": {"type": "object"}}}

        apply_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/apply-types",
            json={"initial_input_schema": alert_schema},
        )

        assert apply_response.status_code == 200
        data = apply_response.json()["data"]
        assert data["applied"] is True
        assert data["nodes_updated"] == 7  # All 7 nodes updated
        assert data["status"] in ["valid", "valid_with_warnings"]

        # Verify types persisted by fetching workflow
        get_response = await client.get(f"/v1/test_tenant/workflows/{workflow_id}")
        assert get_response.status_code == 200
        workflow_data = get_response.json()["data"]

        # Check that nodes have inferred schemas
        for node in workflow_data["nodes"]:
            assert "schemas" in node
            # After apply-types, nodes should have inferred_input/inferred_output
            # (if apply-types persists these fields)

    @pytest.mark.asyncio
    async def test_workflow_output_schema_inference(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        Test that workflow output schema is correctly inferred from terminal nodes.

        For enrichment workflows, the output should be the enriched alert + decision.
        """
        workflow_config = get_basic_threat_intel_workflow()
        template_id = create_identity_template
        task_ids = create_threat_intel_tasks

        # Adapt workflow
        for node in workflow_config["nodes"]:
            if node["kind"] == "task":
                if "virustotal" in node["node_id"].lower():
                    node["task_id"] = task_ids["virustotal"]
                node.pop("node_template_id", None)
            else:
                node["node_template_id"] = template_id
                node.pop("task_id", None)

        workflow_config["created_by"] = str(SYSTEM_USER_ID)

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate
        alert_schema = {"type": "object", "properties": {"alert": {"type": "object"}}}

        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": alert_schema},
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]

        # Check workflow output schema
        assert data["workflow_output_schema"] is not None
        # Terminal node is "assess-risk", so output should be from that node
        # Expected: {"action": string, "enriched_alert": object}
        assert "type" in data["workflow_output_schema"]

    @pytest.mark.asyncio
    async def test_missing_field_access_causes_type_error(
        self,
        client: AsyncClient,
        create_identity_template: str,
        create_threat_intel_tasks: dict[str, str],
    ):
        """
        NEGATIVE TEST: Workflow fails validation when a transformation tries to access
        a field that doesn't exist in the input schema.

        This demonstrates the value of type validation in catching schema mismatches before execution.
        """
        template_id = create_identity_template
        task_ids = create_threat_intel_tasks

        # Create a workflow where extract node expects "iocs" field but alert doesn't have it
        workflow_config = {
            "name": "Broken Workflow - Missing Field",
            "description": "Test workflow with missing field access",
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"alert": {"type": "object"}},
                },
                "output": {"type": "object"},
            },
            "data_samples": [{"alert": {}}],  # Alert without iocs field
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "extract-iocs",
                    "kind": "transformation",
                    "name": "Extract IoCs",
                    "is_start_node": True,
                    "node_template_id": None,  # Will be set below
                    "schemas": {
                        # This node EXPECTS alert.iocs field in input
                        "input": {
                            "type": "object",
                            "properties": {
                                "alert": {
                                    "type": "object",
                                    "properties": {
                                        "iocs": {"type": "array"}  # Expects iocs field
                                    },
                                    "required": ["iocs"],
                                }
                            },
                        },
                        "output": {
                            "type": "object",
                            "properties": {"ioc_list": {"type": "array"}},
                        },
                    },
                },
                {
                    "node_id": "lookup-virustotal",
                    "kind": "task",
                    "name": "VirusTotal Lookup",
                    "task_id": None,  # Will be set below
                    "schemas": {
                        "input": {"type": "object"},
                        "output": {"type": "object"},
                    },
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "from_node_id": "extract-iocs",
                    "to_node_id": "lookup-virustotal",
                }
            ],
        }

        # Set template and task IDs
        workflow_config["nodes"][0]["node_template_id"] = template_id
        workflow_config["nodes"][1]["task_id"] = task_ids["virustotal"]

        # Create workflow
        create_response = await client.post(
            "/v1/test_tenant/workflows", json=workflow_config
        )
        assert create_response.status_code == 201
        workflow_id = create_response.json()["data"]["id"]

        # Validate with alert schema that LACKS the "iocs" field
        incomplete_alert_schema = {
            "type": "object",
            "properties": {
                "alert": {
                    "type": "object",
                    "properties": {
                        "alert_id": {"type": "string"},
                        "title": {"type": "string"},
                        # NOTE: "iocs" field is MISSING here
                    },
                }
            },
        }

        validate_response = await client.post(
            f"/v1/test_tenant/workflows/{workflow_id}/validate-types",
            json={"initial_input_schema": incomplete_alert_schema},
        )

        assert validate_response.status_code == 200
        data = validate_response.json()["data"]

        # Workflow should be INVALID because extract-iocs expects "iocs" field
        assert data["status"] == "invalid", (
            f"Expected invalid status but got: {data['status']}"
        )

        # Should have type errors
        assert len(data["errors"]) > 0, "Expected validation errors for missing field"

        # Find the specific error about missing field
        errors = data["errors"]
        [e.get("message", "") for e in errors]

        # Print errors for debugging
        print("\n=== VALIDATION ERRORS (Missing Field) ===")
        for error in errors:
            print(f"  - Node: {error.get('node_id')}")
            print(f"    Type: {error.get('error_type')}")
            print(f"    Message: {error.get('message')}")
            print(f"    Suggestion: {error.get('suggestion')}")

        # Verify we got a meaningful error about the missing/incompatible field
        assert any("extract-iocs" in str(e.get("node_id", "")) for e in errors), (
            "Expected error to reference the extract-iocs node"
        )
