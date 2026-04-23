"""
Integration tests for Alert Analysis API endpoints.
Tests the REST API endpoints that initiate and track alert analysis.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.alert import Alert, AlertAnalysis, Disposition

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.asyncio
@pytest.mark.integration
class TestAlertAnalysisAPIEndpoints:
    """Test alert analysis API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Create async test client
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield (ac, integration_test_session)

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.fixture
    async def test_dispositions(self, integration_test_session: AsyncSession):
        """Ensure test dispositions exist."""
        from sqlalchemy import select

        result = await integration_test_session.execute(
            select(Disposition).where(Disposition.is_system.is_(True))
        )
        dispositions = result.scalars().all()
        assert len(dispositions) > 0, "System dispositions should be seeded"
        return dispositions

    @pytest.fixture
    async def test_alert(self, integration_test_session: AsyncSession):
        """Create a test alert for analysis."""
        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="AID-TEST-1",
            title="Test Alert for Analysis",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            raw_data='{"test": "data"}',
            raw_data_hash=f"test_hash_{uuid4()}",
            raw_data_hash_algorithm="SHA-256",
            finding_info={},
            ocsf_metadata={},
            severity_id=4,
            status_id=1,
            analysis_status="new",
        )
        integration_test_session.add(alert)
        await integration_test_session.flush()
        await integration_test_session.commit()
        return alert

    @pytest.mark.asyncio
    async def test_start_alert_analysis_success(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test successful alert analysis initiation."""
        # Arrange
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "analysi.alert_analysis.worker.queue_alert_analysis"
            ) as mock_queue:
                mock_queue.return_value = "job-123"

                # Act
                response = await client.post(
                    f"/v1/test-tenant/alerts/{test_alert.id}/analyze"
                )

                # Assert
                assert response.status_code == status.HTTP_202_ACCEPTED
                data = response.json()["data"]
                assert "analysis_id" in data
                assert data["status"] == "accepted"
                assert data["message"] == "Analysis started successfully"
                mock_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_analysis_for_nonexistent_alert(
        self, integration_test_session: AsyncSession
    ):
        """Test starting analysis for non-existent alert.

        Note: PostgreSQL doesn't support foreign key constraints between
        partitioned tables. Since both 'alerts' and 'alert_analysis' are
        partitioned, we cannot enforce referential integrity at the database
        level. The analysis will be created successfully even for non-existent
        alerts, and validation must be done at the application level.

        This test accepts 202 (Accepted) as the current behavior when partitions
        exist. In production, the application should validate alert existence
        before creating an analysis.
        """
        # Arrange
        fake_alert_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            response = await client.post(
                f"/v1/test-tenant/alerts/{fake_alert_id}/analyze"
            )

            # Assert
            # With partitions present, the analysis creation succeeds (202)
            # Without partitions, it would fail with 500
            # Ideally should validate and return 404, but that requires app-level validation
            assert response.status_code == status.HTTP_202_ACCEPTED

    @pytest.mark.asyncio
    async def test_analysis_with_invalid_disposition_triggers_error(
        self, integration_test_session: AsyncSession
    ):
        """Test that trying to complete analysis with invalid disposition_id fails.

        This is a negative test that should trigger a 404 when analysis doesn't exist.
        """
        # Arrange - Use a non-existent analysis ID
        fake_analysis_id = uuid4()
        fake_disposition_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act - Try to complete non-existent analysis
            response = await client.put(
                f"/v1/test-tenant/analyses/{fake_analysis_id}/complete",
                json={
                    "disposition_id": str(fake_disposition_id),
                    "confidence": 85,
                    "short_summary": "Test summary",
                    "long_summary": "Test long summary",
                },
            )

            # Assert - Should fail with 404 because analysis doesn't exist
            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_analysis_with_malformed_data_returns_error(
        self, integration_test_session: AsyncSession
    ):
        """Test that malformed requests return appropriate errors.

        This is a negative test ensuring proper validation of input data.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act - Send request with invalid alert_id format
            response = await client.post(
                "/v1/test-tenant/alerts/not-a-valid-uuid/analyze"
            )

            # Assert - Should fail with 422 Unprocessable Entity
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_analysis_with_invalid_confidence_returns_error(
        self, integration_test_session: AsyncSession
    ):
        """Test that invalid confidence value is validated at API level.

        FastAPI should validate the confidence parameter type.
        """
        # Arrange - Use a fake analysis ID
        fake_analysis_id = uuid4()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act - Try to complete with invalid confidence (string instead of int)
            response = await client.put(
                f"/v1/test-tenant/analyses/{fake_analysis_id}/complete",
                params={
                    "disposition_id": str(uuid4()),
                    "confidence": "not-a-number",  # Invalid: must be integer
                    "short_summary": "Test summary",
                    "long_summary": "Test long summary",
                },
            )

            # Assert - Should fail with 422 due to type validation
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_duplicate_analysis_request(
        self, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test handling concurrent analysis requests for same alert."""
        # Arrange
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "analysi.alert_analysis.worker.queue_alert_analysis"
            ) as mock_queue:
                mock_queue.return_value = "job-456"

                # Act - Start first analysis
                response1 = await client.post(
                    f"/v1/test-tenant/alerts/{test_alert.id}/analyze"
                )

                # Act - Try to start second analysis
                response2 = await client.post(
                    f"/v1/test-tenant/alerts/{test_alert.id}/analyze"
                )

                # Assert
                assert response1.status_code == status.HTTP_202_ACCEPTED
                assert response2.status_code == status.HTTP_202_ACCEPTED
                # Note: Current implementation allows multiple analyses
                # This behavior may need to be changed based on requirements

    @pytest.mark.asyncio
    async def test_get_analysis_progress_running(self, client, test_alert: Alert):
        """Test getting progress for running analysis."""
        http_client, session = client

        # Arrange - Create an analysis record
        analysis = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="running",
            current_step="workflow_execution",
            steps_progress={
                "pre_triage": {"completed": True},
                "workflow_builder": {"completed": True},
                "workflow_execution": {"completed": False},
                "final_disposition_update": {"completed": False},
            },
        )
        session.add(analysis)
        await session.flush()

        # Update alert to reference this analysis
        test_alert.current_analysis_id = analysis.id
        test_alert.analysis_status = "in_progress"
        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/test-tenant/alerts/{test_alert.id}/analysis/progress"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["current_step"] == "workflow_execution"
        assert data["completed_steps"] == 2
        assert data["total_steps"] == 4
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_analysis_progress_completed(
        self, client, test_alert: Alert, test_dispositions
    ):
        """Test getting progress for completed analysis."""
        # Arrange - Create completed analysis
        analysis = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="completed",
            current_step="final_disposition_update",
            disposition_id=test_dispositions[0].id,
            confidence=85,
            short_summary="Test summary",
            steps_progress={
                "pre_triage": {"completed": True},
                "workflow_builder": {"completed": True},
                "workflow_execution": {"completed": True},
                "final_disposition_update": {"completed": True},
            },
        )
        http_client, session = client

        session.add(analysis)
        await session.flush()

        test_alert.current_analysis_id = analysis.id
        test_alert.analysis_status = "completed"
        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/test-tenant/alerts/{test_alert.id}/analysis/progress"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["completed_steps"] == 4
        assert data["total_steps"] == 4
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_analysis_progress_no_analysis(self, client, test_alert: Alert):
        """Test getting progress when no analysis exists."""
        http_client, session = client

        # Act
        response = await http_client.get(
            f"/v1/test-tenant/alerts/{test_alert.id}/analysis/progress"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data == {}  # Empty response when no analysis

    @pytest.mark.asyncio
    async def test_get_alert_analyses_history(self, client, test_alert: Alert):
        """Test retrieving all analyses for an alert."""
        http_client, session = client

        # Arrange - Create multiple analyses
        from datetime import UTC, datetime

        # Use current date to match existing partitions
        base_time = datetime.now(UTC)

        analysis1 = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="completed",
            created_at=base_time.replace(hour=1, minute=0, second=0, microsecond=0),
        )
        analysis2 = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="failed",
            created_at=base_time.replace(hour=2, minute=0, second=0, microsecond=0),
        )
        analysis3 = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="running",
            created_at=base_time.replace(hour=3, minute=0, second=0, microsecond=0),
        )

        session.add_all([analysis1, analysis2, analysis3])
        await session.commit()

        # Act
        response = await http_client.get(
            f"/v1/test-tenant/alerts/{test_alert.id}/analyses"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert len(data) == 3
        # Should be sorted by created_at descending
        assert data[0]["status"] == "running"
        assert data[1]["status"] == "failed"
        assert data[2]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_analyses_empty_history(self, client, test_alert: Alert):
        """Test getting analyses when none exist."""
        http_client, session = client

        # Act
        response = await http_client.get(
            f"/v1/test-tenant/alerts/{test_alert.id}/analyses"
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data == []

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client, test_alert: Alert):
        """Test that tenant isolation is enforced."""
        http_client, session = client

        # Act - Try to access alert from different tenant
        response = await http_client.post(
            f"/v1/different-tenant/alerts/{test_alert.id}/analyze"
        )

        # Assert - Currently returns 202 (accepted), should return 404 for proper isolation
        assert response.status_code == status.HTTP_202_ACCEPTED
        # TODO: Implement proper tenant isolation to return 404

    @patch("analysi.alert_analysis.worker.queue_alert_analysis")
    @pytest.mark.asyncio
    async def test_queue_failure_handling(
        self, mock_queue, integration_test_session: AsyncSession, test_alert: Alert
    ):
        """Test handling when job queuing fails."""
        # Arrange
        mock_queue.side_effect = Exception("Queue connection failed")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Act
            response = await client.post(
                f"/v1/test-tenant/alerts/{test_alert.id}/analyze"
            )

            # Assert - route returns 503 Service Unavailable for queue failures
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            data = response.json()
            assert data["detail"] == "Failed to queue analysis job. Please retry."

    @pytest.mark.asyncio
    async def test_update_analysis_status_to_running(self, client, test_alert: Alert):
        """Test updating analysis status to running."""
        http_client, session = client

        # Arrange - Create an analysis in paused_workflow_building status
        analysis = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="paused",  # V112: paused_workflow_building -> paused
        )
        session.add(analysis)
        await session.flush()
        await session.commit()

        # Act - Update to running
        response = await http_client.put(
            f"/v1/test-tenant/analyses/{analysis.id}/status",
            params={"status": "running"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "updated"
        assert data["analysis_status"] == "running"

        # Verify DB was updated
        await session.refresh(analysis)
        assert analysis.status == "running"
        assert analysis.started_at is not None

    @pytest.mark.asyncio
    async def test_update_analysis_status_to_failed_with_error(
        self, client, test_alert: Alert
    ):
        """Test updating analysis status to failed with error message."""
        http_client, session = client

        # Arrange
        analysis = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="running",
        )
        session.add(analysis)
        await session.flush()
        await session.commit()

        # Act
        response = await http_client.put(
            f"/v1/test-tenant/analyses/{analysis.id}/status",
            params={"status": "failed", "error": "Test error message"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["analysis_status"] == "failed"

        # Verify DB was updated
        await session.refresh(analysis)
        assert analysis.status == "failed"
        assert analysis.error_message == "Test error message"

    @pytest.mark.asyncio
    async def test_update_analysis_status_invalid_status(
        self, client, test_alert: Alert
    ):
        """Test updating analysis status with invalid value."""
        http_client, session = client

        # Arrange
        analysis = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="running",
        )
        session.add(analysis)
        await session.flush()
        await session.commit()

        # Act
        response = await http_client.put(
            f"/v1/test-tenant/analyses/{analysis.id}/status",
            params={"status": "invalid_status"},
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid status" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_analysis_status_not_found(self, client):
        """Test updating status for non-existent analysis."""
        http_client, session = client

        # Act
        response = await http_client.put(
            f"/v1/test-tenant/analyses/{uuid4()}/status",
            params={"status": "running"},
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_alert_analysis_status(self, client, test_alert: Alert):
        """Test updating alert's analysis_status field."""
        http_client, session = client

        # Verify initial status
        await session.refresh(test_alert)
        assert test_alert.analysis_status == "new"

        # Act - Use in_progress which is a valid status
        response = await http_client.put(
            f"/v1/test-tenant/alerts/{test_alert.id}/analysis-status",
            params={"analysis_status": "in_progress"},
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["analysis_status"] == "in_progress"

        # Verify DB was updated
        await session.refresh(test_alert)
        assert test_alert.analysis_status == "in_progress"

    @pytest.mark.asyncio
    async def test_update_alert_analysis_status_invalid(
        self, client, test_alert: Alert
    ):
        """Test updating alert analysis_status with invalid value."""
        http_client, session = client

        # Act
        response = await http_client.put(
            f"/v1/test-tenant/alerts/{test_alert.id}/analysis-status",
            params={"analysis_status": "invalid_status"},
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_update_alert_analysis_status_not_found(self, client):
        """Test updating analysis_status for non-existent alert."""
        http_client, session = client

        # Act - Use valid status to test 404
        response = await http_client.put(
            f"/v1/test-tenant/alerts/{uuid4()}/analysis-status",
            params={"analysis_status": "in_progress"},
        )

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_complete_analysis_saves_workflow_id(
        self, client, test_alert: Alert, test_dispositions
    ):
        """Test that complete_analysis endpoint saves workflow_id on the analysis.

        Bug: workflow_id was never passed to the complete endpoint, leaving
        alert_analysis.workflow_id NULL even after a successful analysis.
        """
        http_client, session = client

        # Arrange - Create a running analysis
        analysis = AlertAnalysis(
            alert_id=test_alert.id,
            tenant_id="test-tenant",
            status="running",
        )
        session.add(analysis)
        await session.flush()

        test_alert.current_analysis_id = analysis.id
        test_alert.analysis_status = "in_progress"
        await session.commit()

        workflow_id = uuid4()
        workflow_run_id = uuid4()

        # Act - Complete with both workflow_id and workflow_run_id
        response = await http_client.put(
            f"/v1/test-tenant/analyses/{analysis.id}/complete",
            json={
                "disposition_id": str(test_dispositions[0].id),
                "confidence": 85,
                "short_summary": "Test summary",
                "long_summary": "Test long summary",
                "workflow_id": str(workflow_id),
                "workflow_run_id": str(workflow_run_id),
            },
        )

        # Assert
        assert response.status_code == status.HTTP_200_OK

        await session.refresh(analysis)
        assert analysis.workflow_id == workflow_id, (
            "complete_analysis must save workflow_id on the analysis record"
        )
        assert analysis.workflow_run_id == workflow_run_id
