"""Integration tests for human_readable_id counter-based generation."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from analysi.repositories.alert_repository import AlertRepository


@pytest.mark.integration
class TestHumanIdCounters:
    """Test human_readable_id counter-based generation and uniqueness."""

    @pytest.fixture
    def alert_repo(self, integration_test_session):
        """Create AlertRepository instance."""
        return AlertRepository(integration_test_session)

    @pytest.fixture(autouse=True)
    async def cleanup_counters(self, integration_test_session):
        """Clean up counter table before each test."""
        await integration_test_session.execute(text("DELETE FROM alert_id_counters"))
        await integration_test_session.commit()
        yield
        # Cleanup after test too
        await integration_test_session.execute(text("DELETE FROM alert_id_counters"))
        await integration_test_session.commit()

    @pytest.mark.asyncio
    async def test_counter_initialization(self, alert_repo, integration_test_session):
        """Test that counter is initialized correctly for new tenants."""
        # Arrange
        tenant_id = "counter-init-test"

        # Act - Get first ID
        first_id = await alert_repo.get_next_human_readable_id(tenant_id)
        await integration_test_session.commit()

        # Assert - Should be AID-1
        assert first_id == "AID-1"

        # Check counter table
        result = await integration_test_session.execute(
            text("SELECT counter FROM alert_id_counters WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        counter = result.scalar()
        assert counter == 1

    @pytest.mark.asyncio
    async def test_id_not_reused_after_deletion(
        self, alert_repo, integration_test_session
    ):
        """Test that human_readable_ids are not reused after alert deletion."""
        # Arrange
        tenant_id = "no-reuse-test"

        # Get first ID and create alert
        id1 = await alert_repo.get_next_human_readable_id(tenant_id)
        alert1 = await alert_repo.create_with_deduplication(
            tenant_id=tenant_id,
            raw_data_hash="hash1",
            human_readable_id=id1,
            title="First Alert",
            triggering_event_time=datetime.now(UTC),
            severity="medium",
            severity_id=3,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data='{"test": 1}',
            raw_data_hash_algorithm="SHA-256",
        )
        await integration_test_session.commit()

        assert id1 == "AID-1"

        # Delete the alert
        deleted = await alert_repo.delete(alert1.id, tenant_id)
        await integration_test_session.commit()
        assert deleted is True

        # Verify alert is deleted
        result = await integration_test_session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE id = :alert_id"),
            {"alert_id": alert1.id},
        )
        assert result.scalar() == 0

        # Get next ID - should be AID-2, not AID-1 (counter keeps incrementing)
        next_id = await alert_repo.get_next_human_readable_id(tenant_id)
        assert next_id == "AID-2"

        # Create second alert - should get AID-2
        alert2 = await alert_repo.create_with_deduplication(
            tenant_id=tenant_id,
            raw_data_hash="hash2",
            human_readable_id=next_id,
            title="Second Alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            severity_id=4,
            status_id=1,
            finding_info={},
            ocsf_metadata={},
            raw_data='{"test": 2}',
            raw_data_hash_algorithm="SHA-256",
        )
        await integration_test_session.commit()

        assert alert2.human_readable_id == "AID-2"

    @pytest.mark.asyncio
    async def test_concurrent_id_generation(self, integration_test_engine):
        """Test that concurrent ID generation works correctly with separate sessions."""
        import asyncio

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        tenant_id = "concurrent-test"

        # Create session factory
        async_session_factory = async_sessionmaker(
            integration_test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Simulate concurrent ID generation - each with its own session
        async def get_id_with_own_session():
            async with async_session_factory() as session:
                repo = AlertRepository(session)
                next_id = await repo.get_next_human_readable_id(tenant_id)
                await session.commit()
                return next_id

        # Generate 5 IDs concurrently - each with its own session
        tasks = [get_id_with_own_session() for _ in range(5)]
        ids = await asyncio.gather(*tasks)

        # All IDs should be unique
        assert len(set(ids)) == len(ids)
        # IDs should be sequential (though order may vary due to concurrency)
        expected_ids = [f"AID-{i}" for i in range(1, 6)]
        assert sorted(ids) == expected_ids

    @pytest.mark.asyncio
    async def test_sequential_id_generation(self, alert_repo, integration_test_session):
        """Test that IDs are generated sequentially."""
        # Arrange
        tenant_id = "sequential-test"

        # Generate multiple IDs
        ids = []
        for _i in range(5):
            next_id = await alert_repo.get_next_human_readable_id(tenant_id)
            ids.append(next_id)

        await integration_test_session.commit()

        # Assert - IDs should be sequential
        assert ids == ["AID-1", "AID-2", "AID-3", "AID-4", "AID-5"]

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, alert_repo, integration_test_session):
        """Test that each tenant has independent ID sequences."""
        # Generate IDs for tenant A
        tenant_a = "tenant-a-isolation"
        ids_a = []
        for _i in range(3):
            next_id = await alert_repo.get_next_human_readable_id(tenant_a)
            ids_a.append(next_id)

        # Generate IDs for tenant B
        tenant_b = "tenant-b-isolation"
        ids_b = []
        for _i in range(2):
            next_id = await alert_repo.get_next_human_readable_id(tenant_b)
            ids_b.append(next_id)

        await integration_test_session.commit()

        # Each tenant should have their own sequence starting from 1
        assert ids_a == ["AID-1", "AID-2", "AID-3"]
        assert ids_b == ["AID-1", "AID-2"]

        # Check counter table directly
        result_a = await integration_test_session.execute(
            text("SELECT counter FROM alert_id_counters WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_a},
        )
        assert result_a.scalar() == 3

        result_b = await integration_test_session.execute(
            text("SELECT counter FROM alert_id_counters WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_b},
        )
        assert result_b.scalar() == 2

    @pytest.mark.asyncio
    async def test_counter_persistence_after_deletion(
        self, alert_repo, integration_test_session
    ):
        """Test that counter continues to increment after alert deletion."""
        # Arrange
        tenant_id = "counter-persist-test"
        alert_ids = []

        # Generate 3 IDs and create alerts
        for i in range(3):
            next_id = await alert_repo.get_next_human_readable_id(tenant_id)
            alert = await alert_repo.create_with_deduplication(
                tenant_id=tenant_id,
                raw_data_hash=f"hash_persist_{i + 1}",
                human_readable_id=next_id,
                title=f"Persist Alert {i + 1}",
                triggering_event_time=datetime.now(UTC),
                severity="low",
                severity_id=2,
                status_id=1,
                finding_info={},
                ocsf_metadata={},
                raw_data=f'{{"persist": {i + 1}}}',
                raw_data_hash_algorithm="SHA-256",
            )
            await integration_test_session.commit()
            alert_ids.append(alert.id)

        # Delete the middle alert (should not affect counter)
        await alert_repo.delete(alert_ids[1], tenant_id)
        await integration_test_session.commit()

        # Verify counter is still at 3
        result = await integration_test_session.execute(
            text("SELECT counter FROM alert_id_counters WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        assert result.scalar() == 3

        # Next ID should be AID-4 (counter keeps incrementing)
        next_id = await alert_repo.get_next_human_readable_id(tenant_id)
        assert next_id == "AID-4"

        # Counter should now be 4
        result = await integration_test_session.execute(
            text("SELECT counter FROM alert_id_counters WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        assert result.scalar() == 4
