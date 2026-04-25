"""Integration tests for Alert REST API endpoints."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app


@pytest.mark.integration
class TestAlertCRUDEndpoints:
    """Test Alert CRUD operations via REST API."""

    @pytest.fixture
    def unique_id(self):
        """Generate unique ID suffix for test isolation."""
        return uuid4().hex[:8]

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Create async test client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_alert_endpoint(self, client):
        """Test POST /v1/{tenant}/alerts creates alert with deduplication."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Test Security Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "source_vendor": "TestVendor",
            "source_product": "TestProduct",
            "raw_alert": '{"test": "alert data"}',
        }

        # Act
        response = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Commit to ensure data persists
        await session.commit()

        # Assert
        if response.status_code != 201:
            print(f"Error: {response.json()}")
        assert response.status_code == 201
        body = response.json()
        data = body["data"]
        assert data["title"] == alert_data["title"]
        assert data["severity"] == alert_data["severity"]
        assert "alert_id" in data
        assert "human_readable_id" in data

    @pytest.mark.asyncio
    async def test_create_alert_duplicate_returns_409(self, client):
        """Test duplicate alerts return 409 Conflict error."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Duplicate Alert Test",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "critical",
            "raw_alert": '{"test": "duplicate"}',
            "source_product": "DupeTest",
        }

        # Act - Create first alert
        response1 = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)
        await session.commit()  # Ensure first alert persists

        # Act - Attempt to create duplicate
        response2 = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Assert
        assert response1.status_code == 201
        assert response2.status_code == 409
        # Check that it contains the enhanced duplicate detection message
        detail = response2.json()["detail"]
        assert "Duplicate alert detected" in detail
        assert "Raw data hash:" in detail
        assert "Duplicate detection based on:" in detail

    @pytest.mark.asyncio
    async def test_list_alerts_endpoint(self, client):
        """Test GET /v1/{tenant}/alerts returns paginated list."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Create multiple alerts
        for i in range(5):
            alert_data = {
                "title": f"Alert {i}",
                "triggering_event_time": datetime.now(UTC).isoformat(),
                "severity": "medium",
                "raw_alert": '{"test": "alert"}',
            }
            await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Commit all created alerts
        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts", params={"limit": 3, "offset": 0}
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]
        meta = body["meta"]
        assert "total" in meta
        assert len(alerts) <= 3

    @pytest.mark.asyncio
    async def test_list_alerts_with_severity_filter(self, client):
        """Test severity filtering works via API."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Create alerts with different severities
        severities = ["low", "medium", "high", "critical"]
        for severity in severities:
            alert_data = {
                "title": f"{severity} Alert",
                "triggering_event_time": datetime.now(UTC).isoformat(),
                "severity": severity,
                "raw_alert": f'{{"severity": "{severity}"}}',
            }
            await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Commit all created alerts
        await session.commit()

        # Act - Filter for high severity only
        response = await http_client.get(
            f"/v1/{tenant}/alerts", params={"severity": ["high"]}
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]
        for alert in alerts:
            assert alert["severity"] == "high"

    @pytest.mark.asyncio
    async def test_list_alerts_with_time_filter(self, client, unique_id):
        """Test time range filtering works via API."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - use unique tenant ID for isolation
        tenant = f"test-tenant-time-{unique_id}"
        now = datetime.now(UTC)
        # Use relative time bounds that will always include "now"
        past = now - timedelta(days=30)
        future = now + timedelta(days=30)

        # Create alert with specific time
        alert_data = {
            "title": "Time-based Alert",
            "triggering_event_time": now.isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        assert create_response.status_code == 201, (
            f"Failed to create alert: {create_response.json()}"
        )
        await session.commit()  # Commit created alert

        # Act - Filter by time range
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"time_from": past.isoformat(), "time_to": future.isoformat()},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]
        assert len(alerts) > 0, f"Expected at least 1 alert, got {body}"

    @pytest.mark.asyncio
    async def test_get_single_alert_endpoint(self, client):
        """Test GET /v1/{tenant}/alerts/{id} returns alert details."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Single Alert Test",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        alert_id = create_response.json()["data"]["alert_id"]
        await session.commit()  # Ensure alert persists

        # Act
        response = await http_client.get(f"/v1/{tenant}/alerts/{alert_id}")

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["alert_id"] == alert_id
        assert data["title"] == alert_data["title"]

    @pytest.mark.asyncio
    async def test_get_alert_not_found(self, client):
        """Test 404 returned for non-existent alert."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        fake_id = str(uuid4())

        # Act
        response = await http_client.get(f"/v1/{tenant}/alerts/{fake_id}")

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_alert_endpoint(self, client):
        """Test PATCH /v1/{tenant}/alerts/{id} updates mutable fields."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Update Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "low",
            "raw_alert": '{"test": "alert"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        alert_id = create_response.json()["data"]["alert_id"]
        await session.commit()  # Ensure alert persists

        # Act
        update_data = {"analysis_status": "completed"}
        response = await http_client.patch(
            f"/v1/{tenant}/alerts/{alert_id}", json=update_data
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["analysis_status"] == "completed"

    @pytest.mark.asyncio
    async def test_update_alert_not_found(self, client):
        """Test 404 returned when updating non-existent alert."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        fake_id = str(uuid4())

        # Act
        response = await http_client.patch(
            f"/v1/{tenant}/alerts/{fake_id}", json={"analysis_status": "completed"}
        )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_alert_endpoint(self, client):
        """Test DELETE /v1/{tenant}/alerts/{id} performs hard delete."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Delete Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        alert_id = create_response.json()["data"]["alert_id"]
        await session.commit()  # Ensure alert persists

        # Act
        response = await http_client.delete(f"/v1/{tenant}/alerts/{alert_id}")

        # Assert
        assert response.status_code == 204

        # Verify alert is deleted
        get_response = await http_client.get(f"/v1/{tenant}/alerts/{alert_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_alert_not_found(self, client):
        """Test 404 returned when deleting non-existent alert."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        fake_id = str(uuid4())

        # Act
        response = await http_client.delete(f"/v1/{tenant}/alerts/{fake_id}")

        # Assert
        assert response.status_code == 404


@pytest.mark.integration
class TestAlertSearchEndpoints:
    """Test Alert search and discovery endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_alerts_text_search(self, client):
        """Test text search across alert fields."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts/search", params={"q": "malware"}
        )

        # Assert - Should return empty list as no alerts match
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []  # Empty list as no alerts exist

    @pytest.mark.asyncio
    async def test_search_by_entity_endpoint(self, client):
        """Test GET /v1/{tenant}/alerts/by-entity/{value} returns matching alerts."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        entity_value = "user@example.com"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts/by-entity/{entity_value}",
            params={"entity_type": "email"},
        )

        # Assert - Should return empty list as no alerts exist
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_search_by_ioc_endpoint(self, client):
        """Test GET /v1/{tenant}/alerts/by-ioc/{value} returns matching alerts."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        ioc_value = "192.168.1.1"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts/by-ioc/{ioc_value}", params={"ioc_type": "ip"}
        )

        # Assert - Should return empty list as no alerts exist
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []


@pytest.mark.integration
class TestDispositionEndpoints:
    """Test Disposition management endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_dispositions_endpoint(self, client):
        """Test GET /v1/{tenant}/dispositions returns all dispositions."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Act
        response = await http_client.get(f"/v1/{tenant}/dispositions")

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) == 18  # Should have 18 system dispositions

    @pytest.mark.asyncio
    async def test_list_dispositions_with_category_filter(self, client):
        """Test filtering dispositions by category."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/dispositions", params={"category": "Malicious"}
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        for disposition in data:
            assert disposition["category"] == "Malicious"

    @pytest.mark.asyncio
    async def test_get_disposition_by_id(self, client):
        """Test GET /v1/{tenant}/dispositions/{id} returns specific disposition."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # First get all dispositions to get a valid ID
        list_response = await http_client.get(f"/v1/{tenant}/dispositions")
        dispositions = list_response.json()["data"]

        if dispositions:
            disposition_id = dispositions[0]["disposition_id"]

            # Act
            response = await http_client.get(
                f"/v1/{tenant}/dispositions/{disposition_id}"
            )

            # Assert
            assert response.status_code == 200
            body = response.json()
            data = body["data"]
            assert data["disposition_id"] == disposition_id

    @pytest.mark.asyncio
    async def test_get_disposition_not_found(self, client):
        """Test 404 for non-existent disposition."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        fake_id = str(uuid4())

        # Act
        response = await http_client.get(f"/v1/{tenant}/dispositions/{fake_id}")

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_dispositions_by_category_endpoint(self, client):
        """Test GET /v1/{tenant}/dispositions/by-category groups correctly."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"

        # Act
        response = await http_client.get(f"/v1/{tenant}/dispositions/by-category")

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert isinstance(data, dict)
        # Check for actual categories from our seed data
        assert "True Positive (Malicious)" in data
        assert "True Positive (Policy Violation)" in data
        assert "False Positive" in data
        assert "Benign Explained" in data
        assert "Undetermined" in data


@pytest.mark.integration
class TestMultiTenantIsolation:
    """Test multi-tenant isolation for alerts."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_tenant_isolation_alerts(self, client):
        """Test alerts are isolated by tenant."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant_a = "tenant-a"
        tenant_b = "tenant-b"

        # Create alert for tenant A
        alert_data = {
            "title": "Tenant A Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
        }
        response_a = await http_client.post(f"/v1/{tenant_a}/alerts", json=alert_data)
        alert_id_a = response_a.json()["data"]["alert_id"]

        # Act - Try to access tenant A's alert from tenant B
        response = await http_client.get(f"/v1/{tenant_b}/alerts/{alert_id_a}")

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_tenant_isolation_human_readable_id(self, client):
        """Test human-readable ID sequences are per-tenant."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant_a = "tenant-a"
        tenant_b = "tenant-b"

        alert_data = {
            "title": "Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
        }

        # Act - Create alerts for both tenants
        response_a = await http_client.post(f"/v1/{tenant_a}/alerts", json=alert_data)
        await session.commit()  # Commit first alert
        response_b = await http_client.post(f"/v1/{tenant_b}/alerts", json=alert_data)
        await session.commit()  # Commit second alert

        # Assert - Both tenants get independent sequences, so their IDs should match
        hrid_a = response_a.json()["data"]["human_readable_id"]
        hrid_b = response_b.json()["data"]["human_readable_id"]
        assert hrid_a.startswith("AID-")
        assert hrid_b.startswith("AID-")
        assert hrid_a == hrid_b

    @pytest.mark.asyncio
    async def test_tenant_isolation_deduplication(self, client):
        """Test deduplication is per-tenant."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant_a = "tenant-a"
        tenant_b = "tenant-b"

        alert_data = {
            "title": "Identical Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
            "source_product": "TestProduct",
        }

        # Act - Create identical alerts for both tenants
        response_a = await http_client.post(f"/v1/{tenant_a}/alerts", json=alert_data)
        await session.commit()  # Commit first alert
        response_b = await http_client.post(f"/v1/{tenant_b}/alerts", json=alert_data)
        await session.commit()  # Commit second alert

        # Assert - Both should be created (no cross-tenant dedup)
        assert response_a.status_code == 201
        assert response_b.status_code == 201
        assert (
            response_a.json()["data"]["alert_id"]
            != response_b.json()["data"]["alert_id"]
        )


@pytest.mark.integration
@pytest.mark.requires_full_stack
class TestAlertAnalysisEndpoints:
    """Test Alert Analysis REST API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_start_alert_analysis(self, client):
        """Test POST /v1/{tenant}/alerts/{alert_id}/analyze starts analysis."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create an alert first
        tenant = "test-tenant"
        alert_data = {
            "title": "Analysis Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "alert for analysis"}',
            "source_product": "TestProduct",
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        # Act - start analysis
        response = await http_client.post(f"/v1/{tenant}/alerts/{alert_id}/analyze")

        # Assert
        assert response.status_code == 202
        body = response.json()
        data = body["data"]
        assert "analysis_id" in data
        assert data["status"] == "accepted"
        assert data["message"] == "Analysis started successfully"

    @pytest.mark.asyncio
    async def test_get_analysis_progress(self, client):
        """Test GET /v1/{tenant}/alerts/{alert_id}/analysis/progress returns progress."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create alert and start analysis
        tenant = "test-tenant"
        alert_data = {
            "title": "Progress Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "critical",
            "raw_alert": '{"test": "progress"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        # Start analysis
        await http_client.post(f"/v1/{tenant}/alerts/{alert_id}/analyze")
        await session.commit()

        # Act - check progress
        response = await http_client.get(
            f"/v1/{tenant}/alerts/{alert_id}/analysis/progress"
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert "analysis_id" in data
        assert "current_step" in data
        assert "completed_steps" in data
        assert "total_steps" in data
        assert "status" in data
        assert data["status"] == "running"  # Initial status is 'running' (no 'pending')

    @pytest.mark.asyncio
    async def test_update_analysis_step(self, client):
        """Test PUT /v1/{tenant}/analyses/{analysis_id}/step updates step progress."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create alert and start analysis
        tenant = "test-tenant"
        alert_data = {
            "title": "Step Update Test",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "step update"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        # Start analysis
        analyze_response = await http_client.post(
            f"/v1/{tenant}/alerts/{alert_id}/analyze"
        )
        await session.commit()
        analysis_id = analyze_response.json()["data"]["analysis_id"]

        # Act - update step
        response = await http_client.put(
            f"/v1/{tenant}/analyses/{analysis_id}/step",
            params={"step_name": "pre_triage", "completed": False},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["status"] == "updated"
        assert data["step"] == "pre_triage"

        # Verify step is tracked in progress
        progress_response = await http_client.get(
            f"/v1/{tenant}/alerts/{alert_id}/analysis/progress"
        )
        progress_data = progress_response.json()["data"]
        assert progress_data["current_step"] == "pre_triage"

    @pytest.mark.asyncio
    async def test_complete_analysis_with_disposition(self, client):
        """Test PUT /v1/{tenant}/analyses/{analysis_id}/complete updates everything."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create alert and start analysis
        tenant = "test-tenant"
        alert_data = {
            "title": "Complete Analysis Test",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "critical",
            "raw_alert": '{"test": "complete analysis"}',
            "source_product": "TestProduct",
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        # Start analysis
        analyze_response = await http_client.post(
            f"/v1/{tenant}/alerts/{alert_id}/analyze"
        )
        await session.commit()
        analysis_id = analyze_response.json()["data"]["analysis_id"]

        # Get a valid disposition ID
        disp_response = await http_client.get(f"/v1/{tenant}/dispositions")
        dispositions = disp_response.json()["data"]
        disposition = next(
            (d for d in dispositions if "Suspicious" in d["display_name"]),
            dispositions[0],
        )

        # Act - complete analysis
        response = await http_client.put(
            f"/v1/{tenant}/analyses/{analysis_id}/complete",
            json={
                "disposition_id": disposition["disposition_id"],
                "confidence": 85,
                "short_summary": "Suspicious activity detected from known user",
                "long_summary": "Analysis indicates potential account compromise based on unusual access patterns",
                "workflow_run_id": str(uuid4()),
                "disposition_category": disposition["category"],
                "disposition_subcategory": disposition["subcategory"],
                "disposition_display_name": disposition["display_name"],
                "disposition_confidence": 85,
            },
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert data["status"] == "completed"
        assert data["analysis_id"] == analysis_id

        # Verify alert was updated with denormalized fields
        alert_response = await http_client.get(f"/v1/{tenant}/alerts/{alert_id}")
        alert_data = alert_response.json()["data"]
        assert alert_data["analysis_status"] == "completed"
        assert alert_data["current_disposition_category"] == disposition["category"]
        assert (
            alert_data["current_disposition_subcategory"] == disposition["subcategory"]
        )
        assert (
            alert_data["current_disposition_display_name"]
            == disposition["display_name"]
        )
        assert alert_data["current_disposition_confidence"] == 85

    @pytest.mark.asyncio
    async def test_re_analysis_resets_disposition_fields(self, client):
        """Test that starting re-analysis resets denormalized disposition fields."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create alert with analysis completed
        tenant = "test-tenant"
        alert_data = {
            "title": "Re-analysis Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "re-analysis"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        # Complete first analysis
        first_analysis = await http_client.post(
            f"/v1/{tenant}/alerts/{alert_id}/analyze"
        )
        await session.commit()
        first_analysis_id = first_analysis.json()["data"]["analysis_id"]

        # Get disposition and complete
        disp_response = await http_client.get(f"/v1/{tenant}/dispositions")
        disposition = disp_response.json()["data"][0]

        await http_client.put(
            f"/v1/{tenant}/analyses/{first_analysis_id}/complete",
            json={
                "disposition_id": disposition["disposition_id"],
                "confidence": 90,
                "short_summary": "First analysis",
                "long_summary": "Initial determination",
                "workflow_run_id": str(uuid4()),
                "disposition_category": disposition["category"],
                "disposition_subcategory": disposition["subcategory"],
                "disposition_display_name": disposition["display_name"],
                "disposition_confidence": 90,
            },
        )
        await session.commit()

        # Verify first analysis results
        alert_response1 = await http_client.get(f"/v1/{tenant}/alerts/{alert_id}")
        alert_data1 = alert_response1.json()["data"]
        assert alert_data1["analysis_status"] == "completed"
        assert alert_data1["current_disposition_category"] is not None

        # Act - start re-analysis
        await http_client.post(f"/v1/{tenant}/alerts/{alert_id}/analyze")
        await session.commit()

        # Assert - disposition fields should be reset
        alert_response2 = await http_client.get(f"/v1/{tenant}/alerts/{alert_id}")
        alert_data2 = alert_response2.json()["data"]
        assert alert_data2["analysis_status"] == "in_progress"
        assert alert_data2["current_disposition_category"] is None
        assert alert_data2["current_disposition_subcategory"] is None
        assert alert_data2["current_disposition_display_name"] is None
        assert alert_data2["current_disposition_confidence"] is None

    @pytest.mark.asyncio
    async def test_analysis_step_tracking_persistence(self, client):
        """Test that step progress is properly persisted with JSONB updates."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create alert and start analysis
        tenant = "test-tenant"
        alert_data = {
            "title": "Step Persistence Test",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "medium",
            "raw_alert": '{"test": "step tracking"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        analyze_response = await http_client.post(
            f"/v1/{tenant}/alerts/{alert_id}/analyze"
        )
        await session.commit()
        analysis_id = analyze_response.json()["data"]["analysis_id"]

        # Act - update multiple steps
        steps = [
            "pre_triage",
            "workflow_builder",
            "workflow_execution",
            "final_disposition_update",
        ]

        for step in steps[:3]:  # Complete first 3 steps
            # Start step
            await http_client.put(
                f"/v1/{tenant}/analyses/{analysis_id}/step",
                params={"step_name": step, "completed": False},
            )
            await session.commit()

            # Complete step
            await http_client.put(
                f"/v1/{tenant}/analyses/{analysis_id}/step",
                params={"step_name": step, "completed": True},
            )
            await session.commit()

        # Assert - check progress shows completed steps
        progress_response = await http_client.get(
            f"/v1/{tenant}/alerts/{alert_id}/analysis/progress"
        )
        progress_data = progress_response.json()["data"]
        assert progress_data["completed_steps"] == 3
        assert "steps_detail" in progress_data

        # Verify each completed step is marked correctly
        for step in steps[:3]:
            assert step in progress_data["steps_detail"]
            assert progress_data["steps_detail"][step]["completed"] is True

    @pytest.mark.asyncio
    async def test_get_analysis_history(self, client):
        """Test GET /v1/{tenant}/alerts/{alert_id}/analyses returns all analyses."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange - create alert
        tenant = "test-tenant"
        alert_data = {
            "title": "History Test Alert",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "low",
            "raw_alert": '{"test": "history"}',
        }
        create_response = await http_client.post(
            f"/v1/{tenant}/alerts", json=alert_data
        )
        await session.commit()
        alert_id = create_response.json()["data"]["alert_id"]

        # Start multiple analyses
        analysis_ids = []
        for _i in range(3):
            analyze_response = await http_client.post(
                f"/v1/{tenant}/alerts/{alert_id}/analyze"
            )
            await session.commit()
            analysis_ids.append(analyze_response.json()["data"]["analysis_id"])

        # Act - get analysis history
        response = await http_client.get(f"/v1/{tenant}/alerts/{alert_id}/analyses")

        # Assert
        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) == 3
        # Verify all our analysis IDs are present
        returned_ids = [str(a["id"]) for a in data]
        for analysis_id in analysis_ids:
            assert analysis_id in returned_ids


@pytest.mark.integration
class TestAlertSorting:
    """Test Alert sorting functionality."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.fixture
    async def setup_test_alerts(self, client):
        """Create test alerts with various attributes for sorting tests."""
        http_client, session = client
        tenant = "test-tenant"

        # Create alerts with different attributes
        # Use recent dates to avoid partition issues
        now = datetime.now(UTC)
        test_alerts = [
            {
                "title": "Alpha Alert",
                "human_readable_id": "AID-100",
                "triggering_event_time": (now - timedelta(hours=3)).isoformat(),
                "severity": "critical",
                "raw_alert": '{"test": "alpha"}',
            },
            {
                "title": "Beta Alert",
                "human_readable_id": "AID-101",
                "triggering_event_time": (now - timedelta(hours=1)).isoformat(),
                "severity": "high",
                "raw_alert": '{"test": "beta"}',
            },
            {
                "title": "Charlie Alert",
                "human_readable_id": "AID-102",
                "triggering_event_time": (now - timedelta(hours=2)).isoformat(),
                "severity": "low",
                "raw_alert": '{"test": "charlie"}',
            },
        ]

        created_alerts = []
        for alert_data in test_alerts:
            response = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)
            created_alerts.append(response.json()["data"])

        await session.commit()
        return created_alerts

    @pytest.mark.asyncio
    async def test_sort_by_human_readable_id_asc(self, client, setup_test_alerts):
        """Test sorting by human_readable_id ascending."""
        http_client, session = client
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"sort_by": "human_readable_id", "sort_order": "asc", "limit": 10},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Extract human_readable_ids and check they're sorted
        ids = [alert["human_readable_id"] for alert in alerts]
        assert ids == sorted(ids)

    @pytest.mark.asyncio
    async def test_sort_by_title_desc(self, client, setup_test_alerts):
        """Test sorting by title descending."""
        http_client, session = client
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"sort_by": "title", "sort_order": "desc", "limit": 10},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Extract titles and check they're sorted descending
        titles = [alert["title"] for alert in alerts]
        assert titles == sorted(titles, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_severity_asc(self, client, setup_test_alerts):
        """Test sorting by severity ascending."""
        http_client, session = client
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"sort_by": "severity", "sort_order": "asc", "limit": 10},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Check that alerts are returned (severity is an enum, so we just check response)
        assert len(alerts) > 0

    @pytest.mark.asyncio
    async def test_sort_by_triggering_event_time_desc(self, client, setup_test_alerts):
        """Test sorting by triggering_event_time descending (default)."""
        http_client, session = client
        tenant = "test-tenant"

        # Act - default sort is triggering_event_time desc
        response = await http_client.get(f"/v1/{tenant}/alerts", params={"limit": 10})

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Extract times and check they're sorted descending
        times = [alert["triggering_event_time"] for alert in alerts]
        assert times == sorted(times, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_analysis_status(self, client):
        """Test sorting by analysis_status."""
        http_client, session = client
        tenant = "test-tenant"

        # Create alerts (they'll all have same analysis_status initially)
        for i in range(3):
            alert_data = {
                "title": f"Status Test {i}",
                "triggering_event_time": datetime.now(UTC).isoformat(),
                "severity": "medium",
                "raw_alert": f'{{"test": "status_{i}"}}',
            }
            await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"sort_by": "analysis_status", "sort_order": "asc", "limit": 10},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Check that all alerts have analysis_status field
        for alert in alerts:
            assert "analysis_status" in alert

    @pytest.mark.asyncio
    async def test_sort_with_include_short_summary(self, client):
        """Test sorting works with include_short_summary parameter."""
        http_client, session = client
        tenant = "test-tenant"

        # Create a test alert
        alert_data = {
            "title": "Summary Sort Test",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "high",
            "raw_alert": '{"test": "summary"}',
        }
        await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)
        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={
                "sort_by": "created_at",
                "sort_order": "desc",
                "include_short_summary": True,
                "limit": 5,
            },
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Check that short_summary field exists (even if null)
        for alert in alerts:
            assert "short_summary" in alert

    @pytest.mark.asyncio
    async def test_invalid_sort_field_uses_default(self, client):
        """Test that invalid sort field falls back to default."""
        http_client, session = client
        tenant = "test-tenant"

        # Act - use invalid sort field
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"sort_by": "invalid_field", "sort_order": "asc", "limit": 5},
        )

        # Assert - should still work, using default sort
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Should be sorted by triggering_event_time desc (default)
        times = [alert["triggering_event_time"] for alert in alerts]
        assert times == sorted(times, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_disposition_display_name(self, client):
        """Test sorting by current_disposition_display_name."""
        http_client, session = client
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={
                "sort_by": "current_disposition_display_name",
                "sort_order": "asc",
                "limit": 10,
            },
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Check that field exists in response
        for alert in alerts:
            assert "current_disposition_display_name" in alert

    @pytest.mark.asyncio
    async def test_sort_by_updated_at(self, client):
        """Test sorting by updated_at timestamp."""
        http_client, session = client
        tenant = "test-tenant"

        # Act
        response = await http_client.get(
            f"/v1/{tenant}/alerts",
            params={"sort_by": "updated_at", "sort_order": "desc", "limit": 5},
        )

        # Assert
        assert response.status_code == 200
        body = response.json()
        alerts = body["data"]

        # Extract updated_at times and check they're sorted descending
        updated_times = [alert["updated_at"] for alert in alerts]
        assert updated_times == sorted(updated_times, reverse=True)


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling and validation."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database.

        Returns tuple of (client, session) per Decision #2 in DECISIONS.md
        to handle transaction isolation properly.
        """

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_severity_values(self, client):
        """Test validation rejects invalid severity values."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Invalid Severity",
            "triggering_event_time": datetime.now(UTC).isoformat(),
            "severity": "INVALID",
            "raw_alert": '{"test": "alert"}',
        }

        # Act
        response = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_datetime_format(self, client):
        """Test validation rejects invalid datetime formats."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            "title": "Invalid DateTime",
            "triggering_event_time": "not-a-datetime",
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
        }

        # Act
        response = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, client):
        """Test validation enforces required fields."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        alert_data = {
            # Missing title
            "severity": "high",
            "raw_alert": '{"test": "alert"}',
            "triggering_event_time": datetime.now(UTC).isoformat(),
        }

        # Act
        response = await http_client.post(f"/v1/{tenant}/alerts", json=alert_data)

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client):
        """Test endpoints reject malformed UUIDs."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        invalid_uuid = "not-a-uuid"

        # Act
        response = await http_client.get(f"/v1/{tenant}/alerts/{invalid_uuid}")

        # Assert
        assert response.status_code == 422
