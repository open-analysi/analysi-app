"""Integration tests for Cy Alert Functions."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.alert import Alert
from analysi.services.cy_alert_functions import (
    CyAlertFunctions,
    create_cy_alert_functions,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestCyAlertFunctionsIntegration:
    """Integration tests for Cy alert functions with real database."""

    @pytest.fixture
    async def test_alert(self, integration_test_session: AsyncSession) -> Alert:
        """Create a test alert in the database."""
        alert = Alert(
            id=uuid.uuid4(),
            tenant_id="default",
            human_readable_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            title="Integration test alert for Cy functions",
            severity="high",
            severity_id=4,
            status_id=1,
            source_vendor="TestVendor",
            source_product="TestProduct",
            rule_name="Test Detection Rule",
            # OCSF structured fields
            finding_info={},
            ocsf_metadata={},
            actor={
                "user": {"name": "workstation-test-01", "type": "device"},
            },
            observables=[
                {"name": "abc123def456", "type": "Hash", "type_id": 8},
                {"name": "malware.exe", "type": "File Name", "type_id": 7},
                {"name": "192.168.1.50", "type": "IP Address", "type_id": 2},
                {"name": "c2server.evil.com", "type": "Hostname", "type_id": 1},
            ],
            # Timestamps
            triggering_event_time=datetime(2024, 1, 20, 14, 30, 0, tzinfo=UTC),
            detected_at=datetime.now(UTC),
            # Dedup hash
            raw_data_hash="test_hash_" + uuid.uuid4().hex[:16],
            raw_data_hash_algorithm="SHA-256",
            # Raw data (stored as JSON string in DB)
            raw_data=json.dumps(
                {
                    "original_source": "EDR System",
                    "event_count": 3,
                    "indicators_of_compromise": [
                        {"value": "malware.exe", "type": "filename"},
                        {"value": "192.168.1.50", "type": "ip"},
                        {"value": "c2server.evil.com", "type": "domain"},
                    ],
                    "risk_entities": [
                        {"value": "test-user", "type": "user"},
                        {"value": "192.168.1.0/24", "type": "network_artifact"},
                    ],
                    "additional_context": {
                        "first_seen": "2024-01-20T14:25:00Z",
                        "last_seen": "2024-01-20T14:30:00Z",
                        "action_taken": "Process terminated and file quarantined",
                    },
                }
            ),
        )

        integration_test_session.add(alert)
        await integration_test_session.flush()

        return alert

    @pytest.mark.asyncio
    async def test_alert_read_integration(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test retrieving an alert from the database using Cy functions."""
        execution_context = {
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
            "tenant_id": "default",
        }

        # Create Cy alert functions
        cy_functions = CyAlertFunctions(
            session=integration_test_session,
            tenant_id="default",
            execution_context=execution_context,
        )

        # Retrieve the alert using alert_read
        alert_data = await cy_functions.alert_read(str(test_alert.id))

        # Verify the data matches what we stored
        assert alert_data["alert_id"] == str(test_alert.id)
        assert alert_data["human_readable_id"] == test_alert.human_readable_id
        assert alert_data["title"] == "Integration test alert for Cy functions"
        assert alert_data["severity"] == "high"
        assert alert_data["severity_id"] == 4
        assert alert_data["source_vendor"] == "TestVendor"
        assert alert_data["source_product"] == "TestProduct"

        # Verify OCSF structured fields
        assert alert_data["actor"]["user"]["name"] == "workstation-test-01"
        observables = alert_data["observables"]
        assert len(observables) == 4
        observable_names = [o["name"] for o in observables]
        assert "abc123def456" in observable_names
        assert "malware.exe" in observable_names
        assert "192.168.1.50" in observable_names
        assert "c2server.evil.com" in observable_names

        # Verify timestamps are ISO formatted strings
        assert "2024-01-20T14:30:00" in alert_data["triggering_event_time"]
        assert isinstance(alert_data["created_at"], str)
        assert "T" in alert_data["created_at"]  # ISO format check

        # Verify raw data is included
        assert alert_data["raw_data"] == test_alert.raw_data
        assert alert_data["raw_data_hash"] == test_alert.raw_data_hash

    @pytest.mark.asyncio
    async def test_alert_read_not_found_integration(
        self, integration_test_session: AsyncSession
    ):
        """Test error handling when alert doesn't exist."""
        execution_context = {
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
            "tenant_id": "default",
        }

        cy_functions = CyAlertFunctions(
            session=integration_test_session,
            tenant_id="default",
            execution_context=execution_context,
        )

        # Try to retrieve non-existent alert
        non_existent_id = str(uuid.uuid4())

        with pytest.raises(ValueError) as exc:
            await cy_functions.alert_read(non_existent_id)

        assert f"Alert {non_existent_id} not found" in str(exc.value)

    @pytest.mark.asyncio
    async def test_alert_read_wrong_tenant_integration(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test that alerts are properly isolated by tenant."""
        execution_context = {
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
            "tenant_id": "different-tenant",
        }

        # Create functions for a different tenant
        cy_functions = CyAlertFunctions(
            session=integration_test_session,
            tenant_id="different-tenant",
            execution_context=execution_context,
        )

        # Should not find the alert from default tenant
        with pytest.raises(ValueError) as exc:
            await cy_functions.alert_read(str(test_alert.id))

        assert "not found for tenant different-tenant" in str(exc.value)

    @pytest.mark.asyncio
    async def test_create_cy_alert_functions_integration(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test the factory function in integration context."""
        execution_context = {
            "task_id": str(uuid.uuid4()),
            "workflow_id": str(uuid.uuid4()),
        }

        # Create functions using factory
        functions = create_cy_alert_functions(
            session=integration_test_session,
            tenant_id="default",
            execution_context=execution_context,
        )

        # Verify alert_read function exists and works
        assert "alert_read" in functions
        alert_func = functions["alert_read"]

        # Test the wrapped function
        alert_data = await alert_func(str(test_alert.id))
        assert alert_data["alert_id"] == str(test_alert.id)
        assert alert_data["title"] == test_alert.title
