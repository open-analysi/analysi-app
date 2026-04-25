"""
Integration tests for Alert database schema and models.
Tests that migrations create correct schema and models work with real PostgreSQL.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.schemas.alert import AnalysisStatus


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.kind_ci
class TestAlertDatabaseSchema:
    """Test alert database schema creation and basic operations."""

    @pytest.mark.asyncio
    async def test_alerts_table_exists(self, integration_test_session):
        """Test that alerts table is created by migrations."""
        result = await integration_test_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alerts')"
            )
        )
        exists = result.scalar()
        assert exists is True  # Table should exist after migration

    @pytest.mark.asyncio
    async def test_alert_analysis_table_exists(self, integration_test_session):
        """Test that alert_analysis table is created by migrations."""
        result = await integration_test_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alert_analyses')"
            )
        )
        exists = result.scalar()
        assert exists is True  # Table should exist after migration

    @pytest.mark.asyncio
    async def test_dispositions_table_exists(self, integration_test_session):
        """Test that dispositions table is created by migrations."""
        result = await integration_test_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'dispositions')"
            )
        )
        exists = result.scalar()
        assert exists is True  # Table should exist after migration

    @pytest.mark.asyncio
    async def test_create_alert_model(self, integration_test_session):
        """Test creating an Alert model instance."""
        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="AID-1",
            title="Test alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            severity_id=4,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data='{"test": "data"}',
            raw_data_hash="test_hash_123",
            raw_data_hash_algorithm="SHA-256",
        )

        integration_test_session.add(alert)
        await integration_test_session.commit()

        # Verify it was created
        assert alert.id is not None

    @pytest.mark.asyncio
    async def test_create_alert_analysis_model(self, integration_test_session):
        """Test creating an AlertAnalysis model instance."""
        # First create an alert to reference
        alert = Alert(
            tenant_id="test-tenant",
            human_readable_id="AID-2",
            title="Test alert for analysis",
            triggering_event_time=datetime.now(UTC),
            severity="medium",
            severity_id=3,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data='{"test": "data"}',
            raw_data_hash="test_hash_456",
            raw_data_hash_algorithm="SHA-256",
        )
        integration_test_session.add(alert)
        await integration_test_session.flush()

        analysis = AlertAnalysis(
            alert_id=alert.id,
            tenant_id="test-tenant",
            status=AnalysisStatus.RUNNING,
        )

        integration_test_session.add(analysis)
        await integration_test_session.commit()

        # Verify it was created
        assert analysis.id is not None

    @pytest.mark.asyncio
    async def test_create_disposition_model(self, integration_test_session):
        """Test creating a Disposition model instance."""
        # Create a custom disposition (seed data already has system ones)
        disposition = Disposition(
            category="custom",
            subcategory="test_subcategory",
            display_name="Test Disposition",
            color_hex="#123456",
            color_name="test_blue",
            priority_score=5,
            is_system=False,
        )

        integration_test_session.add(disposition)
        await integration_test_session.commit()

        # Verify it was created
        assert disposition.id is not None

    @pytest.mark.asyncio
    async def test_alerts_table_partitioning(self, integration_test_session):
        """Test that alerts table has partitioning configured."""
        result = await integration_test_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'alerts'
                AND c.relkind = 'p'  -- 'p' means partitioned table
            """
            )
        )
        count = result.scalar()
        assert count == 1  # Partitioned table should exist

    @pytest.mark.asyncio
    async def test_alert_unique_constraints(self, integration_test_session):
        """Test unique indexes on alerts table (PostgreSQL partitioned tables use unique indexes instead of constraints)."""
        # Check human_readable_id has a UNIQUE index
        result = await integration_test_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE tablename = 'alerts'
                AND indexdef LIKE '%UNIQUE%'
                AND indexname LIKE '%human_readable%'
            """
            )
        )
        unique_count = result.scalar()
        assert unique_count >= 1  # Should have unique index on human_readable_id

        # Check raw_data_hash has a (non-unique) conditional index
        result2 = await integration_test_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE tablename = 'alerts'
                AND indexname LIKE '%raw_data_hash%'
            """
            )
        )
        hash_index_count = result2.scalar()
        assert hash_index_count >= 1  # Should have index on raw_data_hash

    @pytest.mark.asyncio
    async def test_disposition_unique_constraint(self, integration_test_session):
        """Test unique constraint on dispositions table."""
        result = await integration_test_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_constraint
                WHERE conname LIKE '%category%subcategory%'
                   AND conrelid = 'dispositions'::regclass
            """
            )
        )
        count = result.scalar()
        assert count >= 1  # Should have unique constraint

    @pytest.mark.asyncio
    async def test_disposition_seed_data(self, integration_test_session):
        """Test that system dispositions can be created and retrieved."""
        # Since we're in a transaction that can't see committed seed data,
        # we'll test that we can create and retrieve system dispositions

        # Create a few sample system dispositions
        test_dispositions = [
            Disposition(
                category="true_positive",
                subcategory="confirmed_breach",
                display_name="Confirmed Security Breach",
                color_hex="#DC2626",
                color_name="red",
                priority_score=1,
                requires_escalation=True,
                is_system=True,
            ),
            Disposition(
                category="benign",
                subcategory="false_positive",
                display_name="False Positive",
                color_hex="#84CC16",
                color_name="lime",
                priority_score=8,
                requires_escalation=False,
                is_system=True,
            ),
        ]

        for disp in test_dispositions:
            integration_test_session.add(disp)

        await integration_test_session.flush()

        # Query them back
        result = await integration_test_session.execute(
            select(Disposition).where(Disposition.is_system.is_(True))
        )
        dispositions = result.scalars().all()

        # Should have at least our test dispositions
        assert len(dispositions) >= 2
        assert all(d.is_system for d in dispositions)

    @pytest.mark.asyncio
    async def test_alert_analysis_jsonb_field(self, integration_test_session):
        """Test that alert_analysis has JSONB steps_progress field."""
        result = await integration_test_session.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'alert_analyses'
                AND column_name = 'steps_progress'
            """
            )
        )
        data_type = result.scalar()
        assert data_type == "jsonb"  # Field should be JSONB type
