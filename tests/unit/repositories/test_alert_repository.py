"""Unit tests for AlertRepository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.models.alert import Alert, Disposition
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)


class TestAlertRepository:
    """Test AlertRepository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def alert_repo(self, mock_session):
        """Create AlertRepository instance."""
        return AlertRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_with_deduplication_success(self, alert_repo, mock_session):
        """Test successful alert creation when no duplicate exists."""
        # Arrange
        tenant_id = "test-tenant"
        raw_data_hash = "hash123"
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Mock get_next_human_readable_id
        with patch.object(
            alert_repo, "get_next_human_readable_id", return_value="AID-1"
        ):
            # Act
            alert = await alert_repo.create_with_deduplication(
                tenant_id=tenant_id,
                raw_data_hash=raw_data_hash,
                title="Test Alert",
                severity="high",
                triggering_event_time=datetime.now(UTC),
            )

        # Assert
        assert alert is not None
        assert alert.tenant_id == tenant_id
        assert alert.raw_data_hash == raw_data_hash
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_deduplication_duplicate(self, alert_repo, mock_session):
        """Test deduplication prevents duplicate alerts."""
        # Arrange
        tenant_id = "test-tenant"
        raw_data_hash = "hash123"
        existing_alert = MagicMock(spec=Alert)
        mock_session.execute.return_value.scalar_one_or_none.return_value = (
            existing_alert
        )

        # Act
        alert = await alert_repo.create_with_deduplication(
            tenant_id=tenant_id, raw_data_hash=raw_data_hash, title="Test Alert"
        )

        # Assert
        assert alert is None
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_next_human_readable_id(self, alert_repo, mock_session):
        """Test atomic human-readable ID generation per tenant."""
        # Arrange
        tenant_id = "test-tenant"
        mock_result = AsyncMock()
        mock_result.scalar = MagicMock(return_value="AID-5")
        mock_session.execute.return_value = mock_result

        # Act
        human_id = await alert_repo.get_next_human_readable_id(tenant_id)

        # Assert
        assert human_id == "AID-5"

    @pytest.mark.asyncio
    async def test_find_by_filters_severity(self, alert_repo, mock_session):
        """Test filtering alerts by severity levels."""
        # Arrange
        tenant_id = "test-tenant"
        mock_alerts = [MagicMock(spec=Alert) for _ in range(3)]

        # First execute for count query
        mock_count_result = AsyncMock()
        mock_count_result.scalar = MagicMock(return_value=3)

        # Second execute for alerts query
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_alerts)
        mock_alerts_result = AsyncMock()
        mock_alerts_result.scalars = MagicMock(return_value=mock_scalars)

        mock_session.execute.side_effect = [mock_count_result, mock_alerts_result]

        # Act
        alerts, total = await alert_repo.find_by_filters(
            tenant_id=tenant_id, severity=["high", "critical"]
        )

        # Assert
        assert len(alerts) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_find_by_filters_time_range(self, alert_repo, mock_session):
        """Test filtering alerts by time range."""
        # Arrange
        tenant_id = "test-tenant"
        time_from = datetime(2024, 1, 1, tzinfo=UTC)
        time_to = datetime(2024, 1, 31, tzinfo=UTC)
        mock_alerts = [MagicMock(spec=Alert) for _ in range(2)]

        # First execute for count query
        mock_count_result = AsyncMock()
        mock_count_result.scalar = MagicMock(return_value=2)

        # Second execute for alerts query
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_alerts)
        mock_alerts_result = AsyncMock()
        mock_alerts_result.scalars = MagicMock(return_value=mock_scalars)

        mock_session.execute.side_effect = [mock_count_result, mock_alerts_result]

        # Act
        alerts, total = await alert_repo.find_by_filters(
            tenant_id=tenant_id, time_from=time_from, time_to=time_to
        )

        # Assert
        assert len(alerts) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_find_by_filters_pagination(self, alert_repo, mock_session):
        """Test pagination works correctly."""
        # Arrange
        tenant_id = "test-tenant"
        mock_alerts = [MagicMock(spec=Alert) for _ in range(10)]

        # First execute for count query
        mock_count_result = AsyncMock()
        mock_count_result.scalar = MagicMock(return_value=25)

        # Second execute for alerts query
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_alerts)
        mock_alerts_result = AsyncMock()
        mock_alerts_result.scalars = MagicMock(return_value=mock_scalars)

        mock_session.execute.side_effect = [mock_count_result, mock_alerts_result]

        # Act
        alerts, total = await alert_repo.find_by_filters(
            tenant_id=tenant_id, limit=10, offset=10
        )

        # Assert
        assert len(alerts) == 10
        assert total == 25

    @pytest.mark.asyncio
    async def test_find_by_filters_ioc_filter(self, alert_repo, mock_session):
        """Test filtering alerts by IOC value searches observables, evidences, and actor JSONB."""
        tenant_id = "test-tenant"
        mock_alerts = [MagicMock(spec=Alert)]

        mock_count_result = AsyncMock()
        mock_count_result.scalar = MagicMock(return_value=1)

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_alerts)
        mock_alerts_result = AsyncMock()
        mock_alerts_result.scalars = MagicMock(return_value=mock_scalars)

        mock_session.execute.side_effect = [mock_count_result, mock_alerts_result]

        # Act — ioc_filter is the new parameter
        alerts, total = await alert_repo.find_by_filters(
            tenant_id=tenant_id, ioc_filter="91.234.56.17"
        )

        # Assert
        assert len(alerts) == 1
        assert total == 1
        # Verify that execute was called (SQL was generated without error)
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_hard_delete(self, alert_repo, mock_session):
        """Test hard delete removes alert from database."""
        # Arrange
        alert_id = uuid4()
        tenant_id = "test-tenant"
        mock_alert = MagicMock(spec=Alert)
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_alert)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()  # Use AsyncMock for async method

        # Act
        result = await alert_repo.delete(alert_id, tenant_id)

        # Assert
        assert result is True
        mock_session.delete.assert_called_once_with(mock_alert)

    @pytest.mark.asyncio
    async def test_get_by_entity(self, alert_repo, mock_session):
        """Test searching alerts by entity value."""
        # Arrange
        tenant_id = "test-tenant"
        entity_value = "user@example.com"
        entity_type = "user"
        mock_alerts = [MagicMock(spec=Alert) for _ in range(2)]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_alerts)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        # Act
        alerts = await alert_repo.get_by_entity(tenant_id, entity_value, entity_type)

        # Assert
        assert len(alerts) == 2

    @pytest.mark.asyncio
    async def test_get_by_ioc(self, alert_repo, mock_session):
        """Test searching alerts by IOC value."""
        # Arrange
        tenant_id = "test-tenant"
        ioc_value = "192.168.1.1"
        ioc_type = "ip"
        mock_alerts = [MagicMock(spec=Alert) for _ in range(3)]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_alerts)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        # Act
        alerts = await alert_repo.get_by_ioc(tenant_id, ioc_value, ioc_type)

        # Assert
        assert len(alerts) == 3


class TestAlertAnalysisRepository:
    """Test AlertAnalysisRepository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def analysis_repo(self, mock_session):
        """Create AlertAnalysisRepository instance."""
        return AlertAnalysisRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_analysis(self, analysis_repo, mock_session):
        """Test creating new analysis for an alert."""
        # Arrange
        alert_id = uuid4()
        tenant_id = "test-tenant"

        # Act
        analysis = await analysis_repo.create_analysis(alert_id, tenant_id)

        # Assert
        assert analysis is not None
        assert analysis.alert_id == alert_id
        assert analysis.tenant_id == tenant_id
        assert analysis.status == "running"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


class TestDispositionRepository:
    """Test DispositionRepository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def disposition_repo(self, mock_session):
        """Create DispositionRepository instance."""
        return DispositionRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_all_system_dispositions(self, disposition_repo, mock_session):
        """Test retrieving all system dispositions."""
        # Arrange
        mock_dispositions = [MagicMock(spec=Disposition) for _ in range(18)]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_dispositions)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        # Act
        dispositions = await disposition_repo.get_all_system_dispositions()

        # Assert
        assert len(dispositions) == 18

    @pytest.mark.asyncio
    async def test_get_by_category(self, disposition_repo, mock_session):
        """Test grouping dispositions by category."""
        # Arrange
        benign_disp = MagicMock(spec=Disposition, category="Benign")
        suspicious_disp = MagicMock(spec=Disposition, category="Suspicious")
        malicious_disp = MagicMock(spec=Disposition, category="Malicious")

        mock_dispositions = [benign_disp, suspicious_disp, malicious_disp]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_dispositions)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        # Act
        grouped = await disposition_repo.get_by_category()

        # Assert
        assert "Benign" in grouped
        assert "Suspicious" in grouped
        assert "Malicious" in grouped

    @pytest.mark.asyncio
    async def test_find_by_priority_range(self, disposition_repo, mock_session):
        """Test filtering dispositions by priority score."""
        # Arrange
        mock_dispositions = [MagicMock(spec=Disposition) for _ in range(5)]
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_dispositions)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        # Act
        dispositions = await disposition_repo.find_by_priority_range(50, 100)

        # Assert
        assert len(dispositions) == 5
