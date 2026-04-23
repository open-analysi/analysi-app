"""Test re-analysis synchronization between alerts and analysis tables."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)
from analysi.schemas.alert import AlertCreate, AlertSeverity
from analysi.services.alert_service import AlertAnalysisService, AlertService


@pytest.mark.integration
@pytest.mark.asyncio
class TestReanalysisSync:
    """Test that re-analysis properly syncs alert and analysis tables."""

    @pytest.mark.asyncio
    async def test_reanalysis_resets_disposition_fields(
        self, integration_test_session: AsyncSession
    ):
        """Test that starting re-analysis resets the denormalized disposition fields."""
        # Create a test alert
        alert_repo = AlertRepository(integration_test_session)
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        disposition_repo = DispositionRepository(integration_test_session)
        alert_service = AlertService(
            alert_repo, analysis_repo, disposition_repo, integration_test_session
        )

        alert_create = AlertCreate(
            title="Test Alert for Re-analysis",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.HIGH,
            raw_alert="test raw alert",
        )

        alert = await alert_service.create_alert("test_tenant", alert_create)

        # Manually set some disposition fields as if a previous analysis completed
        stmt = select(Alert).where(Alert.id == alert.alert_id)
        result = await integration_test_session.execute(stmt)
        alert_db = result.scalar_one()

        alert_db.analysis_status = "completed"
        alert_db.current_disposition_category = "True Positive (Malicious)"
        alert_db.current_disposition_subcategory = "Confirmed Compromise"
        alert_db.current_disposition_display_name = "Confirmed Compromise"
        alert_db.current_disposition_confidence = 85

        await integration_test_session.commit()

        # Now start a new analysis (re-analysis)
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        analysis_service = AlertAnalysisService(
            analysis_repo, alert_repo, integration_test_session
        )

        new_analysis = await analysis_service.start_analysis(
            "test_tenant", alert.alert_id
        )
        await integration_test_session.commit()

        # Verify the alert's disposition fields were reset
        await integration_test_session.refresh(alert_db)

        assert alert_db.analysis_status == "in_progress"
        assert alert_db.current_analysis_id == new_analysis.id
        assert alert_db.current_disposition_category is None
        assert alert_db.current_disposition_subcategory is None
        assert alert_db.current_disposition_display_name is None
        assert alert_db.current_disposition_confidence is None

    @pytest.mark.asyncio
    async def test_analysis_completion_updates_alert_fields(
        self, integration_test_session: AsyncSession
    ):
        """Test that completing an analysis updates the alert's denormalized fields."""
        # Create test alert
        alert_repo = AlertRepository(integration_test_session)
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        disposition_repo = DispositionRepository(integration_test_session)
        alert_service = AlertService(
            alert_repo, analysis_repo, disposition_repo, integration_test_session
        )

        alert_create = AlertCreate(
            title="Test Alert for Completion",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.MEDIUM,
            raw_alert="test raw alert",
        )

        alert = await alert_service.create_alert("test_tenant", alert_create)

        # Start analysis
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        analysis_service = AlertAnalysisService(
            analysis_repo, alert_repo, integration_test_session
        )

        analysis = await analysis_service.start_analysis("test_tenant", alert.alert_id)
        await integration_test_session.commit()

        # Get a test disposition
        stmt = select(Disposition).where(
            Disposition.category == "False Positive",
            Disposition.subcategory == "Detection Logic Error",
        )
        result = await integration_test_session.execute(stmt)
        disposition = result.scalar_one()

        # Mark analysis as completed
        await analysis_service.complete_analysis(
            analysis_id=analysis.id,
            disposition_id=disposition.id,
            confidence=75,
            short_summary="Test summary",
            long_summary="Test long summary",
        )
        await integration_test_session.commit()

        # Check that alert was updated
        stmt = select(Alert).where(Alert.id == alert.alert_id)
        result = await integration_test_session.execute(stmt)
        alert_db = result.scalar_one()

        assert alert_db.analysis_status == "completed"

        # Note: The denormalized fields are updated by FinalDispositionUpdateStep
        # which runs in the worker pipeline, not by complete_analysis directly

    @pytest.mark.asyncio
    async def test_multiple_reanalysis_cycles(
        self, integration_test_session: AsyncSession
    ):
        """Test that multiple re-analysis cycles maintain proper sync."""
        # Create test alert
        alert_repo = AlertRepository(integration_test_session)
        analysis_repo = AlertAnalysisRepository(integration_test_session)
        disposition_repo = DispositionRepository(integration_test_session)
        alert_service = AlertService(
            alert_repo, analysis_repo, disposition_repo, integration_test_session
        )

        alert_create = AlertCreate(
            title="Test Alert Multiple Re-analysis",
            triggering_event_time=datetime.now(UTC),
            severity=AlertSeverity.LOW,
            raw_alert="test raw alert",
        )

        alert = await alert_service.create_alert("test_tenant", alert_create)

        analysis_repo = AlertAnalysisRepository(integration_test_session)
        analysis_service = AlertAnalysisService(
            analysis_repo, alert_repo, integration_test_session
        )

        # Perform 3 re-analysis cycles
        analysis_ids = []
        for i in range(3):
            # Set some disposition data from "previous" analysis
            if i > 0:
                stmt = select(Alert).where(Alert.id == alert.alert_id)
                result = await integration_test_session.execute(stmt)
                alert_db = result.scalar_one()

                alert_db.current_disposition_category = f"Category_{i}"
                alert_db.current_disposition_confidence = i * 30
                await integration_test_session.commit()

            # Start new analysis
            analysis = await analysis_service.start_analysis(
                "test_tenant", alert.alert_id
            )
            analysis_ids.append(analysis.id)
            await integration_test_session.commit()

            # Verify reset
            stmt = select(Alert).where(Alert.id == alert.alert_id)
            result = await integration_test_session.execute(stmt)
            alert_db = result.scalar_one()

            assert alert_db.current_analysis_id == analysis.id
            assert alert_db.analysis_status == "in_progress"
            assert alert_db.current_disposition_category is None
            assert alert_db.current_disposition_confidence is None

        # Verify we have 3 analysis records
        stmt = select(AlertAnalysis).where(AlertAnalysis.alert_id == alert.alert_id)
        result = await integration_test_session.execute(stmt)
        analyses = result.scalars().all()

        assert len(analyses) == 3
        assert {a.id for a in analyses} == set(analysis_ids)
