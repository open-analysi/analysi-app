"""
Integration tests for Alert repository layer.
These tests use a real database connection to test the actual implementations.
"""

from datetime import UTC, datetime

import pytest

from analysi.models.alert import Alert
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)
from analysi.schemas.alert import AnalysisStatus


@pytest.mark.asyncio
@pytest.mark.integration
class TestAlertRepositoryIntegration:
    """Test AlertRepository with real database."""

    @pytest.fixture
    async def alert_repo(self, integration_test_session):
        """Create AlertRepository with real session."""
        return AlertRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_create_with_deduplication(
        self, alert_repo, integration_test_session
    ):
        """Test creating alert with content hash deduplication."""
        # Create first alert
        alert1 = await alert_repo.create_with_deduplication(
            tenant_id="test-tenant",
            raw_data_hash="unique_hash_123",
            human_readable_id="AID-TEST-1",
            title="Test alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            severity_id=4,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data='{"test": "data"}',
            raw_data_hash_algorithm="SHA-256",
        )

        assert alert1 is not None
        assert alert1.raw_data_hash == "unique_hash_123"

        # Try to create duplicate - should return None
        alert2 = await alert_repo.create_with_deduplication(
            tenant_id="test-tenant",
            raw_data_hash="unique_hash_123",
            human_readable_id="AID-TEST-2",
            title="Duplicate alert",
            triggering_event_time=datetime.now(UTC),
            severity="medium",
            severity_id=3,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data='{"duplicate": "data"}',
            raw_data_hash_algorithm="SHA-256",
        )

        assert alert2 is None  # Duplicate detected

    @pytest.mark.asyncio
    async def test_get_next_human_readable_id(self, alert_repo):
        """Test generating next sequential human-readable ID."""
        # First ID should be AID-1 for new tenant
        id1 = await alert_repo.get_next_human_readable_id("new-tenant")
        assert id1 == "AID-1"

        # For existing tenant, it should increment
        # (This depends on existing data in the test session)

    @pytest.mark.asyncio
    async def test_find_by_filters(self, alert_repo, integration_test_session):
        """Test finding alerts with filters."""
        # Create test alerts
        now = datetime.now(UTC)
        alert = Alert(
            tenant_id="filter-test",
            human_readable_id="AID-FILTER-1",
            title="Critical alert",
            triggering_event_time=now,
            severity="critical",
            severity_id=5,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            source_vendor="TestVendor",
            source_product="TestProduct",
            raw_data="{}",
            raw_data_hash="filter_test_hash",
            raw_data_hash_algorithm="SHA-256",
        )
        integration_test_session.add(alert)
        await integration_test_session.flush()

        # Test filtering
        alerts, total = await alert_repo.find_by_filters(
            tenant_id="filter-test",
            severity=["critical"],
            source_vendor="TestVendor",
            limit=10,
            offset=0,
        )

        assert total >= 1
        assert any(a.severity == "critical" for a in alerts)


@pytest.mark.asyncio
@pytest.mark.integration
class TestAlertAnalysisRepositoryIntegration:
    """Test AlertAnalysisRepository with real database."""

    @pytest.fixture
    async def analysis_repo(self, integration_test_session):
        """Create AlertAnalysisRepository with real session."""
        return AlertAnalysisRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_create_and_update_analysis(
        self, analysis_repo, integration_test_session
    ):
        """Test creating and updating analysis."""
        # Create an alert first
        alert = Alert(
            tenant_id="analysis-test",
            human_readable_id="AID-ANALYSIS-1",
            title="Test alert for analysis",
            triggering_event_time=datetime.now(UTC),
            severity="medium",
            severity_id=3,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data="{}",
            raw_data_hash="analysis_test_hash",
            raw_data_hash_algorithm="SHA-256",
        )
        integration_test_session.add(alert)
        await integration_test_session.flush()

        # Create analysis
        analysis = await analysis_repo.create_analysis(
            alert_id=alert.id, tenant_id="analysis-test"
        )

        assert analysis is not None
        assert analysis.status == AnalysisStatus.RUNNING

        # Update step progress
        await analysis_repo.update_step_progress(
            analysis_id=analysis.id, step="pre_triage", completed=True
        )

        # Verify update
        await integration_test_session.refresh(analysis)
        assert "pre_triage" in analysis.steps_progress
        assert analysis.steps_progress["pre_triage"]["completed"] is True


@pytest.mark.asyncio
@pytest.mark.integration
class TestDispositionRepositoryIntegration:
    """Test DispositionRepository with real database."""

    @pytest.fixture
    async def disposition_repo(self, integration_test_session):
        """Create DispositionRepository with real session."""
        return DispositionRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_create_custom_disposition(self, disposition_repo):
        """Test creating custom disposition."""
        disposition = await disposition_repo.create_custom_disposition(
            category="custom_test",
            subcategory="test_sub",
            display_name="Test Disposition",
            color_hex="#123456",
            color_name="test_blue",
            priority_score=5,
            description="Test custom disposition",
            requires_escalation=False,
        )

        assert disposition is not None
        assert disposition.category == "custom_test"
        assert disposition.is_system is False
