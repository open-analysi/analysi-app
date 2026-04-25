"""Integration tests for the complete alert analysis flow."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)
from analysi.schemas.alert import AlertCreate
from analysi.services.alert_service import AlertAnalysisService, AlertService


@pytest.mark.integration
class TestAlertAnalysisFlow:
    """Test the complete alert analysis flow from creation to disposition update."""

    @pytest.fixture
    async def test_client(self, integration_test_session):
        """Create an async HTTP client for testing with test database."""
        from httpx import ASGITransport, AsyncClient

        from analysi.db.session import get_db
        from analysi.main import app

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_alert_analysis_with_disposition(self, db_session: AsyncSession):
        """Test full alert analysis flow including disposition matching."""
        tenant_id = "test_tenant"

        # Create an alert
        alert_data = AlertCreate(
            title="Test Security Alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            source_vendor="TestVendor",
            source_product="TestProduct",
            source_category="EDR",
            alert_type="malware",
            rule_name="Test Rule",
            primary_risk_entity_value="test-user@example.com",
            primary_risk_entity_type="user",
            primary_ioc_value="malicious.exe",
            primary_ioc_type="filename",
            raw_alert="Test alert for integration testing",
        )

        alert_repo = AlertRepository(db_session)
        analysis_repo = AlertAnalysisRepository(db_session)
        disposition_repo = DispositionRepository(db_session)
        alert_service = AlertService(
            alert_repo, analysis_repo, disposition_repo, db_session
        )

        # Create the alert
        created_alert = await alert_service.create_alert(tenant_id, alert_data)
        assert created_alert.alert_id is not None
        assert created_alert.human_readable_id is not None
        assert created_alert.analysis_status == "new"

        # Start analysis
        analysis_repo = AlertAnalysisRepository(db_session)
        analysis_service = AlertAnalysisService(analysis_repo, alert_repo, db_session)

        analysis = await analysis_service.start_analysis(
            tenant_id, created_alert.alert_id
        )
        assert analysis.id is not None
        assert analysis.status == "running"

        # Verify alert was updated
        updated_alert = await alert_service.get_alert(tenant_id, created_alert.alert_id)
        assert updated_alert.analysis_status == "in_progress"
        assert updated_alert.current_analysis_id == analysis.id

        await db_session.commit()

    @pytest.mark.asyncio
    async def test_disposition_api_returns_disposition_id(
        self, integration_test_session: AsyncSession, test_client
    ):
        """Test that disposition API returns disposition_id field."""
        # Get dispositions from API
        response = await test_client.get("/v1/default/dispositions")
        assert response.status_code == 200

        dispositions = response.json()["data"]
        assert len(dispositions) > 0

        # Check that all dispositions have disposition_id field
        for disp in dispositions:
            assert "disposition_id" in disp
            assert "id" not in disp  # Should not have 'id' field
            assert "category" in disp
            assert "display_name" in disp

    @pytest.mark.asyncio
    async def test_analysis_complete_endpoint(
        self, integration_test_session: AsyncSession, test_client
    ):
        """Test the complete analysis API endpoint end-to-end.

        This is a TRUE integration test - no mocking, tests the actual API endpoint.
        """
        tenant_id = "test_tenant"
        alert_id = uuid4()
        analysis_id = uuid4()
        workflow_run_id = uuid4()

        # Create test alert
        alert = Alert(
            id=alert_id,
            tenant_id=tenant_id,
            human_readable_id="TEST-1",
            title="Test Alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            raw_data="Test raw alert",
            raw_data_hash="test_hash_" + str(uuid4()),
            raw_data_hash_algorithm="SHA-256",
            finding_info={},
            ocsf_metadata={},
            severity_id=4,
            status_id=1,
            analysis_status="in_progress",  # Set initial status
            current_analysis_id=analysis_id,  # Link to the analysis
        )
        integration_test_session.add(alert)

        # Create test analysis
        analysis = AlertAnalysis(
            id=analysis_id,
            alert_id=alert_id,
            tenant_id=tenant_id,
            status="running",
            current_step="final_disposition",
        )
        integration_test_session.add(analysis)
        await integration_test_session.commit()

        # Get a real disposition from the database
        from sqlalchemy import select

        stmt = select(Disposition).where(
            Disposition.display_name == "Suspicious Activity"
        )
        result = await integration_test_session.execute(stmt)
        disposition = result.scalar_one_or_none()

        if disposition is None:
            pytest.skip("No 'Suspicious Activity' disposition found in test database")

        # Call the ACTUAL API endpoint (no mocking!)
        response = await test_client.put(
            f"/v1/{tenant_id}/analyses/{analysis_id}/complete",
            json={
                "disposition_id": str(disposition.id),
                "confidence": 85,
                "short_summary": "Test short summary",
                "long_summary": "Test long summary",
                "workflow_run_id": str(workflow_run_id),
                "disposition_category": disposition.category,
                "disposition_subcategory": disposition.subcategory,
                "disposition_display_name": disposition.display_name,
                "disposition_confidence": 85,
            },
        )

        # Verify API response
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["status"] == "completed"
        assert result["analysis_id"] == str(analysis_id)

        # Verify database was updated correctly
        # Re-query instead of refresh() because AlertAnalysis has a composite PK
        # (id, created_at) where created_at is a server default. After the API
        # endpoint commits, the expired server-default column prevents refresh()
        # from constructing the SELECT query.
        stmt = select(AlertAnalysis).where(
            AlertAnalysis.id == analysis_id,
            AlertAnalysis.tenant_id == tenant_id,
        )
        result = await integration_test_session.execute(stmt)
        updated_analysis = result.scalar_one()
        assert updated_analysis.status == "completed"
        assert updated_analysis.disposition_id == disposition.id
        assert updated_analysis.confidence == 85
        assert updated_analysis.short_summary == "Test short summary"
        assert updated_analysis.long_summary == "Test long summary"
        assert updated_analysis.completed_at is not None

        # Verify alert was also updated (Alert also has composite PK with
        # server-default ingested_at, same refresh() issue)
        stmt = select(Alert).where(
            Alert.id == alert_id,
            Alert.tenant_id == tenant_id,
        )
        result = await integration_test_session.execute(stmt)
        updated_alert = result.scalar_one()
        assert updated_alert.analysis_status == "completed"

    @pytest.mark.asyncio
    async def test_disposition_matching_fallbacks(self, db_session: AsyncSession):
        """Test disposition matching with various fallback scenarios."""
        from sqlalchemy import select

        from analysi.alert_analysis.steps.final_disposition_update import (
            FinalDispositionUpdateStep,
        )

        step = FinalDispositionUpdateStep()

        # Get all dispositions
        stmt = select(Disposition).order_by(Disposition.priority_score)
        result = await db_session.execute(stmt)
        dispositions = result.scalars().all()

        # Skip test if no dispositions are available
        if not dispositions:
            pytest.skip("No dispositions available in test database")

        # Convert to the format expected by the step
        disp_list = [
            {
                "disposition_id": str(d.id),
                "category": d.category,
                "subcategory": d.subcategory,
                "display_name": d.display_name,
                "color_hex": d.color_hex,
                "color_name": d.color_name,
                "priority_score": d.priority_score,
                "requires_escalation": d.requires_escalation,
            }
            for d in dispositions
        ]

        # Test 1: Exact match
        result = await step._match_disposition("Confirmed Compromise", disp_list)
        assert "Confirmed Compromise" in result["name"]

        # Test 2: Substring match - display name appears in text
        result = await step._match_disposition(
            "Suspicious Activity detected in the network", disp_list
        )
        assert "Suspicious Activity" in result["name"]

        # Test 3: Structured format match - "CATEGORY / DISPLAY_NAME"
        result = await step._match_disposition(
            "TRUE POSITIVE / Confirmed Compromise", disp_list
        )
        assert "Confirmed Compromise" in result["name"]

        # Test 4: No match - raises ValueError (no silent defaults)
        with pytest.raises(ValueError, match="No disposition match found"):
            await step._match_disposition("Random unmatched text", disp_list)

        # Test 5: Empty text - raises ValueError
        with pytest.raises(ValueError, match="No disposition text provided"):
            await step._match_disposition(None, disp_list)

    @pytest.mark.asyncio
    async def test_confidence_extraction(self, db_session: AsyncSession):
        """Test confidence extraction from various text formats."""
        from analysi.alert_analysis.steps.final_disposition_update import (
            FinalDispositionUpdateStep,
        )

        step = FinalDispositionUpdateStep()

        # Test various formats
        assert step._extract_confidence("85% confidence") == 85
        assert step._extract_confidence("confidence: 90%") == 90
        assert step._extract_confidence("Confidence: 70") == 70
        assert step._extract_confidence("50 percent confidence") == 50

        # Test bounds
        assert step._extract_confidence("150% confidence") == 100  # Max 100
        assert step._extract_confidence("-10% confidence") == 0  # Min 0

        # Test defaults
        assert step._extract_confidence("") == 75
        assert step._extract_confidence(None) == 75
        assert step._extract_confidence("no confidence mentioned") == 75
