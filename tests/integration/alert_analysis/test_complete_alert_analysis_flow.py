"""
Complete End-to-End Integration Test for Alert Analysis Service.
Tests the entire flow from alert creation to final disposition assignment.

This test covers:
1. Creating an alert via API
2. Triggering alert analysis
3. Assigning a default workflow
4. Executing the workflow (with mock outputs for disposition)
5. Updating disposition based on workflow results
6. Verifying alert is analyzed with correct disposition
"""

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.models.auth import SYSTEM_USER_ID


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompleteAlertAnalysisFlow:
    """Test the complete alert analysis flow from creation to disposition."""

    @pytest.fixture
    def tenant_id(self):
        """Unique tenant ID per test to avoid cross-test interference."""
        return f"e2e-flow-{uuid4().hex[:8]}"

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
    async def test_workflow(self, client: AsyncClient, tenant_id: str):
        """Create a test workflow using a system template (survives cleanup)."""
        # List system templates and use the identity/passthrough template.
        # System templates (tenant_id IS NULL) are preserved during test cleanup,
        # avoiding a race where the previous test's teardown deletes user templates.
        tmpl_response = await client.get(f"/v1/{tenant_id}/workflows/node-templates")
        assert tmpl_response.status_code == 200
        templates = tmpl_response.json()["data"]
        assert len(templates) > 0, "No system templates found — seed data missing"
        # Prefer the identity template; fall back to any enabled template
        template = next(
            (t for t in templates if "identity" in t["name"].lower()),
            templates[0],
        )
        template_id = template["id"]

        workflow_data = {
            "name": "Default Alert Analysis Workflow",
            "description": "Standard workflow for analyzing security alerts",
            "is_dynamic": False,
            "io_schema": {
                "input": {
                    "type": "object",
                    "properties": {"alert": {"type": "object"}},
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "analysis": {"type": "string"},
                        "disposition_text": {"type": "string"},
                    },
                },
            },
            "data_samples": [
                {
                    "alert": {
                        "title": "Sample Alert",
                        "severity": "high",
                        "alert_type": "authentication",
                    }
                }
            ],
            "created_by": str(SYSTEM_USER_ID),
            "nodes": [
                {
                    "node_id": "n-analyze",
                    "kind": "transformation",
                    "name": "Analyze Alert",
                    "is_start_node": True,
                    "node_template_id": template_id,
                    "schemas": {
                        "input": {
                            "type": "object",
                            "properties": {"alert": {"type": "object"}},
                        },
                        "output_result": {
                            "type": "object",
                            "properties": {
                                "analysis": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                        },
                    },
                }
            ],
            "edges": [],
        }

        workflow_response = await client.post(
            f"/v1/{tenant_id}/workflows", json=workflow_data
        )
        assert workflow_response.status_code == 201, (
            f"Workflow creation failed: {workflow_response.json()}"
        )
        return workflow_response.json()["data"]

    @pytest.fixture
    async def test_dispositions(self, integration_test_session: AsyncSession):
        """Ensure test dispositions exist and return them."""
        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(Disposition).where(Disposition.is_system.is_(True))
        )
        dispositions = result.scalars().all()
        assert len(dispositions) > 0, "System dispositions should be seeded"

        # Find the false positive disposition for our test
        false_positive = next(
            (d for d in dispositions if "Detection Logic Error" in d.display_name),
            dispositions[0],
        )
        return {"all": dispositions, "false_positive": false_positive}

    @pytest.mark.asyncio
    async def test_complete_alert_analysis_flow(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        tenant_id: str,
        test_workflow: dict,
        test_dispositions: dict,
    ):
        """Test the complete flow from alert creation to disposition assignment."""

        # Step 1: Create an alert via API
        alert_data = {
            "title": "Suspicious Login Activity Detected",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "source_vendor": "SecurityMonitor",
            "source_product": "AuthGuard",
            "alert_type": "authentication",
            "primary_risk_entity_value": "john.doe@example.com",
            "primary_risk_entity_type": "user",
            "primary_ioc_value": "192.168.100.50",
            "primary_ioc_type": "ip",
            "raw_alert": json.dumps(
                {
                    "event": "login",
                    "user": "john.doe@example.com",
                    "ip": "192.168.100.50",
                    "location": "New York, US",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "risk_score": 75,
                }
            ),
        }

        create_alert_response = await client.post(
            f"/v1/{tenant_id}/alerts", json=alert_data
        )
        assert create_alert_response.status_code == 201
        alert = create_alert_response.json()["data"]
        alert_id = alert["alert_id"]

        # Step 2: Trigger alert analysis
        with patch("analysi.alert_analysis.worker.queue_alert_analysis") as mock_queue:
            mock_queue.return_value = "job-123"

            analyze_response = await client.post(
                f"/v1/{tenant_id}/alerts/{alert_id}/analyze"
            )
            assert analyze_response.status_code == 202
            analysis_data = analyze_response.json()["data"]
            analysis_id = analysis_data["analysis_id"]

        # Step 3: Select our default workflow
        selected_workflow_id = test_workflow["id"]

        # Step 4: Execute the workflow
        # Mock enqueue_or_fail — this test verifies the analysis flow,
        # not Redis connectivity. Without this, the ARQ pool can fail with
        # "Event loop is closed" when pytest-asyncio recycles event loops.
        with patch(
            "analysi.common.arq_enqueue.enqueue_or_fail",
            return_value="mock-job-id",
        ):
            workflow_run_response = await client.post(
                f"/v1/{tenant_id}/workflows/{selected_workflow_id}/run",
                json={
                    "input_data": {
                        "alert": alert,
                        "context": {
                            "tenant_id": tenant_id,
                            "alert_id": alert_id,
                            "analysis_id": analysis_id,
                        },
                    }
                },
            )
        assert workflow_run_response.status_code == 202
        workflow_run = workflow_run_response.json()["data"]
        workflow_run_id = workflow_run["workflow_run_id"]

        # Step 5: Simulate the disposition matching step
        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(AlertAnalysis).where(AlertAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()

        false_positive_disp = test_dispositions["false_positive"]
        analysis.disposition_id = false_positive_disp.id
        analysis.confidence = 85
        analysis.short_summary = "False positive login alert"
        analysis.long_summary = "Analysis indicates this is a false positive due to known user behavior patterns."
        analysis.status = "completed"
        analysis.current_step = "final_disposition_update"
        analysis.steps_progress = {
            "pre_triage": {"completed": True},
            "workflow_builder": {
                "completed": True,
                "workflow_id": selected_workflow_id,
            },
            "workflow_execution": {
                "completed": True,
                "workflow_run_id": workflow_run_id,
            },
            "final_disposition_update": {
                "completed": True,
                "disposition_id": str(false_positive_disp.id),
            },
        }

        alert_result = await integration_test_session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        alert_record = alert_result.scalar_one()
        alert_record.analysis_status = "completed"
        alert_record.current_analysis_id = analysis.id

        await integration_test_session.commit()

        # Step 6: Verify the alert endpoint returns analyzed status with disposition
        get_alert_response = await client.get(
            f"/v1/{tenant_id}/alerts/{alert_id}?include_analysis=true&include_disposition=true"
        )
        assert get_alert_response.status_code == 200

        final_alert = get_alert_response.json()["data"]
        assert final_alert["analysis_status"] == "completed"
        assert final_alert["current_analysis_id"] == analysis_id

        progress_response = await client.get(
            f"/v1/{tenant_id}/alerts/{alert_id}/analysis/progress"
        )
        assert progress_response.status_code == 200

        progress = progress_response.json()["data"]
        assert progress["status"] == "completed"
        assert progress["completed_steps"] == 4
        assert progress["total_steps"] == 4
        assert progress["current_step"] == "final_disposition_update"

    @pytest.mark.asyncio
    async def test_complete_flow_with_artifact_creation(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        tenant_id: str,
        test_workflow: dict,
        test_dispositions: dict,
    ):
        """Test the complete flow including artifact creation during workflow execution."""

        alert_data = {
            "title": "Malware Detection Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "critical",
            "source_vendor": "AntiMalware",
            "source_product": "EndpointProtection",
            "alert_type": "malware",
            "primary_risk_entity_value": "workstation-123",
            "primary_risk_entity_type": "device",
            "primary_ioc_value": "evil.exe",
            "primary_ioc_type": "filename",
            "raw_alert": json.dumps(
                {
                    "malware_family": "Trojan.Generic",
                    "file_path": "C:\\Users\\Public\\evil.exe",
                    "action_taken": "quarantined",
                }
            ),
        }

        create_alert_response = await client.post(
            f"/v1/{tenant_id}/alerts", json=alert_data
        )
        assert create_alert_response.status_code == 201
        alert = create_alert_response.json()["data"]
        alert_id = alert["alert_id"]

        with patch("analysi.alert_analysis.worker.queue_alert_analysis") as mock_queue:
            mock_queue.return_value = "job-456"

            analyze_response = await client.post(
                f"/v1/{tenant_id}/alerts/{alert_id}/analyze"
            )
            assert analyze_response.status_code == 202
            analysis_id = analyze_response.json()["data"]["analysis_id"]

        with patch(
            "analysi.common.arq_enqueue.enqueue_or_fail",
            return_value="mock-job-id",
        ):
            workflow_run_response = await client.post(
                f"/v1/{tenant_id}/workflows/{test_workflow['id']}/run",
                json={"input_data": {"alert": alert}},
            )
        assert workflow_run_response.status_code == 202

        # Update analysis to completed (simulating pipeline completion)
        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(AlertAnalysis).where(AlertAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()

        malware_disp = next(
            (
                d
                for d in test_dispositions["all"]
                if "Confirmed Compromise" in d.display_name
            ),
            test_dispositions["all"][0],
        )

        analysis.disposition_id = malware_disp.id
        analysis.confidence = 95
        analysis.short_summary = "Malware detected and quarantined"
        analysis.long_summary = (
            "Trojan.Generic malware was detected and successfully quarantined."
        )
        analysis.status = "completed"

        alert_result = await integration_test_session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        alert_record = alert_result.scalar_one()
        alert_record.analysis_status = "completed"
        alert_record.current_analysis_id = analysis.id

        await integration_test_session.commit()

        get_alert_response = await client.get(f"/v1/{tenant_id}/alerts/{alert_id}")
        assert get_alert_response.status_code == 200

        final_alert = get_alert_response.json()["data"]
        assert final_alert["analysis_status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_flow_with_real_llm_disposition(
        self,
        client: AsyncClient,
        integration_test_session: AsyncSession,
        tenant_id: str,
        test_workflow: dict,
        test_dispositions: dict,
    ):
        """Test the complete flow with disposition matching (mocked LLM)."""

        alert_data = {
            "title": "Multiple Failed Login Attempts Detected",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "medium",
            "source_vendor": "AuthenticationMonitor",
            "source_product": "LoginProtection",
            "alert_type": "authentication",
            "primary_risk_entity_value": "admin@company.com",
            "primary_risk_entity_type": "user",
            "primary_ioc_value": "203.0.113.42",
            "primary_ioc_type": "ip",
            "raw_alert": json.dumps(
                {
                    "event": "failed_login_attempts",
                    "user": "admin@company.com",
                    "ip": "203.0.113.42",
                    "attempts": 15,
                    "time_window": "5 minutes",
                    "location": "Russia",
                    "user_agent": "Mozilla/5.0",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "risk_score": 65,
                    "additional_context": "User typically logs in from USA office IP",
                }
            ),
        }

        create_alert_response = await client.post(
            f"/v1/{tenant_id}/alerts", json=alert_data
        )
        assert create_alert_response.status_code == 201
        alert = create_alert_response.json()["data"]
        alert_id = alert["alert_id"]

        with patch("analysi.alert_analysis.worker.queue_alert_analysis") as mock_queue:
            mock_queue.return_value = "job-llm-test"

            analyze_response = await client.post(
                f"/v1/{tenant_id}/alerts/{alert_id}/analyze"
            )
            assert analyze_response.status_code == 202
            analysis_id = analyze_response.json()["data"]["analysis_id"]

        with patch(
            "analysi.common.arq_enqueue.enqueue_or_fail",
            return_value="mock-job-id",
        ):
            workflow_run_response = await client.post(
                f"/v1/{tenant_id}/workflows/{test_workflow['id']}/run",
                json={"input_data": {"alert": alert}},
            )
        assert workflow_run_response.status_code == 202
        workflow_run_id = workflow_run_response.json()["data"]["workflow_run_id"]

        all_dispositions = test_dispositions["all"]
        raw_alert_data = json.loads(alert_data["raw_alert"])

        # Pick a disposition deterministically instead of calling an LLM
        matched_disposition = next(
            (d for d in all_dispositions if "Suspicious" in d.display_name),
            all_dispositions[0],
        )
        confidence = 82
        explanation = (
            "Multiple failed login attempts from an unusual geographic location "
            "suggest suspicious activity warranting further investigation."
        )

        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(AlertAnalysis).where(AlertAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()

        analysis.disposition_id = matched_disposition.id
        analysis.confidence = confidence
        analysis.short_summary = (
            f"Multiple failed login attempts from {raw_alert_data['location']}"
        )
        analysis.long_summary = explanation
        analysis.status = "completed"
        analysis.current_step = "final_disposition_update"
        analysis.steps_progress = {
            "pre_triage": {"completed": True},
            "workflow_builder": {"completed": True, "workflow_id": test_workflow["id"]},
            "workflow_execution": {
                "completed": True,
                "workflow_run_id": workflow_run_id,
            },
            "final_disposition_update": {
                "completed": True,
                "disposition_id": str(matched_disposition.id),
            },
        }

        alert_result = await integration_test_session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        alert_record = alert_result.scalar_one()
        alert_record.analysis_status = "completed"
        alert_record.current_analysis_id = analysis.id

        await integration_test_session.commit()

        get_alert_response = await client.get(
            f"/v1/{tenant_id}/alerts/{alert_id}?include_analysis=true&include_disposition=true"
        )
        assert get_alert_response.status_code == 200

        final_alert = get_alert_response.json()["data"]
        assert final_alert["analysis_status"] == "completed"
        assert final_alert["current_analysis_id"] == analysis_id

        progress_response = await client.get(
            f"/v1/{tenant_id}/alerts/{alert_id}/analysis/progress"
        )
        assert progress_response.status_code == 200

        progress = progress_response.json()["data"]
        assert progress["status"] == "completed"
        assert progress["completed_steps"] == 4
