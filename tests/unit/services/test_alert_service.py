"""Unit tests for AlertService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.models.alert import Alert, Disposition
from analysi.schemas.alert import AlertCreate, AlertUpdate
from analysi.services.alert_service import (
    AlertService,
    DispositionService,
)


class TestAlertService:
    """Test AlertService methods."""

    def create_mock_alert(self, **overrides):
        """Helper to create properly mocked Alert objects."""
        defaults = {
            "alert_id": uuid4(),
            "tenant_id": "test-tenant",
            "human_readable_id": "AID-1",
            "title": "Test Alert",
            "triggering_event_time": datetime.now(UTC),
            "severity": "high",
            "severity_id": 4,
            "analysis_status": "new",
            "raw_data_hash": "test_hash",
            "raw_data_hash_algorithm": "SHA-256",
            "ingested_at": datetime.now(UTC),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "current_analysis_id": None,
            "raw_data": '{"test": "alert"}',
            "raw_alert": '{"test": "alert"}',  # Alias for raw_data (schema compat)
            "source_vendor": None,
            "source_product": None,
            "rule_name": None,
            "detected_at": None,
            "source_event_id": None,
            # OCSF JSONB fields
            "finding_info": {},
            "ocsf_metadata": {},
            "evidences": None,
            "observables": None,
            "osint": None,
            "actor": None,
            "device": None,
            "cloud": None,
            "vulnerabilities": None,
            "unmapped": None,
            # OCSF scalar enum columns
            "disposition_id": None,
            "verdict_id": None,
            "action_id": None,
            "status_id": 1,
            "confidence_id": None,
            "risk_level_id": None,
            "ocsf_time": None,
            # Disposition fields
            "current_disposition_category": None,
            "current_disposition_subcategory": None,
            "current_disposition_display_name": None,
            "current_disposition_confidence": None,
        }
        defaults.update(overrides)

        mock_alert = MagicMock(spec=Alert)
        for key, value in defaults.items():
            setattr(mock_alert, key, value)
        return mock_alert

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        alert_repo = AsyncMock()
        analysis_repo = AsyncMock()
        disposition_repo = AsyncMock()
        return alert_repo, analysis_repo, disposition_repo

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def alert_service(self, mock_repos, mock_session):
        """Create AlertService instance."""
        alert_repo, analysis_repo, disposition_repo = mock_repos
        return AlertService(alert_repo, analysis_repo, disposition_repo, mock_session)

    @pytest.mark.asyncio
    async def test_create_alert_with_raw_data_hash(self, alert_service, mock_repos):
        """Test alert creation generates correct raw_data_hash."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        alert_data = AlertCreate(
            title="Test Alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            raw_alert='{"test": "alert"}',
            source_product="TestProduct",
        )

        mock_alert = self.create_mock_alert(
            tenant_id=tenant_id,
            source_product="TestProduct",
        )

        alert_repo.create_with_deduplication.return_value = mock_alert
        alert_repo.get_next_human_readable_id.return_value = "AID-1"

        # Act
        with patch.object(
            alert_service, "_calculate_raw_data_hash", return_value="test_hash"
        ):
            await alert_service.create_alert(tenant_id, alert_data)

        # Assert
        alert_repo.create_with_deduplication.assert_called_once()
        call_args = alert_repo.create_with_deduplication.call_args
        assert call_args[1]["raw_data_hash"] == "test_hash"

    @pytest.mark.asyncio
    async def test_create_alert_generates_human_id(self, alert_service, mock_repos):
        """Test human-readable ID is auto-generated when not provided."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        alert_data = AlertCreate(
            title="Test Alert",
            triggering_event_time=datetime.now(UTC),
            severity="high",
            raw_alert='{"test": "alert"}',
        )

        mock_alert = self.create_mock_alert(tenant_id=tenant_id)

        alert_repo.create_with_deduplication.return_value = mock_alert
        alert_repo.get_next_human_readable_id.return_value = "AID-1"

        # Act
        await alert_service.create_alert(tenant_id, alert_data)

        # Assert
        alert_repo.get_next_human_readable_id.assert_called_once_with(tenant_id)

    @pytest.mark.asyncio
    async def test_update_alert_only_mutable_fields(self, alert_service, mock_session):
        """Test only allowed fields can be updated."""
        # Arrange
        tenant_id = "test-tenant"
        alert_id = uuid4()
        update_data = AlertUpdate(analysis_status="completed")

        mock_alert = self.create_mock_alert(alert_id=alert_id, tenant_id=tenant_id)

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_alert)
        mock_session.execute.return_value = mock_result

        # Act
        await alert_service.update_alert(tenant_id, alert_id, update_data)

        # Assert
        assert mock_alert.analysis_status == "completed"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_alerts_with_filters(self, alert_service, mock_repos):
        """Test service correctly applies multiple filters."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        filters = {
            "severity": ["high", "critical"],
            "status": "pending",
            "source_vendor": "TestVendor",
        }

        mock_alerts = []
        for i in range(5):
            mock_alert = self.create_mock_alert(
                tenant_id=tenant_id,
                human_readable_id=f"AID-{i + 1}",
                raw_data_hash="hash123",
            )
            mock_alerts.append(mock_alert)
        alert_repo.find_by_filters.return_value = (mock_alerts, 5)

        # Act
        result = await alert_service.list_alerts(tenant_id, filters, limit=20, offset=0)

        # Assert
        assert result.total == 5
        assert len(result.alerts) == 5
        alert_repo.find_by_filters.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_alert_hard_delete(
        self, alert_service, mock_repos, mock_session
    ):
        """Test delete operation performs hard delete."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        alert_id = uuid4()

        # Mock the delete method to return True
        alert_repo.delete.return_value = True

        # Act
        result = await alert_service.delete_alert(tenant_id, alert_id)

        # Assert
        assert result is True
        alert_repo.delete.assert_called_once_with(alert_id, tenant_id)

    @pytest.mark.asyncio
    async def test_search_alerts(self, alert_service, mock_repos):
        """Test text search functionality."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        query = "search query"
        mock_alerts = []
        for i in range(2):
            mock_alert = self.create_mock_alert(
                tenant_id=tenant_id,
                human_readable_id=f"AID-{i + 1}",
                raw_data_hash="hash123",
            )
            mock_alerts.append(mock_alert)
        alert_repo.search_text.return_value = mock_alerts

        # Act
        results = await alert_service.search_alerts(tenant_id, query)

        # Assert
        assert len(results) == 2
        alert_repo.search_text.assert_called_once_with(tenant_id, query, 20)

    @pytest.mark.asyncio
    async def test_get_alerts_by_entity(self, alert_service, mock_repos):
        """Test search by entity with type filtering."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        entity_value = "user@example.com"
        entity_type = "user"
        mock_alerts = []
        for i in range(3):
            mock_alert = self.create_mock_alert(
                tenant_id=tenant_id,
                human_readable_id=f"AID-{i + 1}",
                raw_data_hash="hash123",
            )
            mock_alerts.append(mock_alert)
        alert_repo.get_by_entity.return_value = mock_alerts

        # Act
        results = await alert_service.get_alerts_by_entity(
            tenant_id, entity_value, entity_type
        )

        # Assert
        assert len(results) == 3
        alert_repo.get_by_entity.assert_called_once_with(
            tenant_id, entity_value, entity_type, 20
        )

    @pytest.mark.asyncio
    async def test_get_alerts_by_ioc(self, alert_service, mock_repos):
        """Test search by IOC with type filtering."""
        # Arrange
        alert_repo, _, _ = mock_repos
        tenant_id = "test-tenant"
        ioc_value = "192.168.1.1"
        ioc_type = "ip"
        mock_alerts = []
        for i in range(4):
            mock_alert = self.create_mock_alert(
                tenant_id=tenant_id,
                human_readable_id=f"AID-{i + 1}",
                raw_data_hash="hash123",
            )
            mock_alerts.append(mock_alert)
        alert_repo.get_by_ioc.return_value = mock_alerts

        # Act
        results = await alert_service.get_alerts_by_ioc(tenant_id, ioc_value, ioc_type)

        # Assert
        assert len(results) == 4
        alert_repo.get_by_ioc.assert_called_once_with(
            tenant_id, ioc_value, ioc_type, 20
        )


class TestDispositionService:
    """Test DispositionService methods."""

    @pytest.fixture
    def mock_disposition_repo(self):
        """Create mock disposition repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def disposition_service(self, mock_disposition_repo, mock_session):
        """Create DispositionService instance."""
        return DispositionService(mock_disposition_repo, mock_session)

    @pytest.mark.asyncio
    async def test_list_dispositions(self, disposition_service, mock_session):
        """Test listing dispositions with filters."""
        # Arrange
        mock_dispositions = []
        for _i, category in enumerate(["Benign", "Malicious"]):
            mock_disp = MagicMock(spec=Disposition)
            mock_disp.id = uuid4()
            mock_disp.category = category
            mock_disp.subcategory = "Test Sub"
            mock_disp.display_name = f"{category} Disposition"
            mock_disp.color_hex = "#00FF00"
            mock_disp.color_name = "green"
            mock_disp.priority_score = 5
            mock_disp.description = "Test description"
            mock_disp.requires_escalation = False
            mock_disp.is_system = True
            mock_disp.created_at = datetime.now(UTC)
            mock_disp.updated_at = datetime.now(UTC)
            mock_dispositions.append(mock_disp)
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=mock_dispositions)
        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        # Act
        result = await disposition_service.list_dispositions(category="Benign")

        # Assert
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_disposition(self, disposition_service, mock_session):
        """Test getting specific disposition by ID."""
        # Arrange
        disposition_id = uuid4()
        mock_disposition = MagicMock(spec=Disposition)
        # Set required attributes for DispositionResponse validation
        mock_disposition.id = disposition_id
        mock_disposition.category = "Benign"
        mock_disposition.subcategory = "Test Sub"
        mock_disposition.display_name = "Test Disposition"
        mock_disposition.color_hex = "#00FF00"
        mock_disposition.color_name = "green"
        mock_disposition.priority_score = 5
        mock_disposition.description = "Test description"
        mock_disposition.requires_escalation = False
        mock_disposition.is_system = True
        mock_disposition.created_at = datetime.now(UTC)
        mock_disposition.updated_at = datetime.now(UTC)

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_disposition)
        mock_session.execute.return_value = mock_result

        # Act
        result = await disposition_service.get_disposition(disposition_id)

        # Assert
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_category(self, disposition_service, mock_disposition_repo):
        """Test getting dispositions grouped by category."""

        # Arrange
        def create_mock_disposition(category):
            mock_disp = MagicMock(spec=Disposition)
            mock_disp.id = uuid4()
            mock_disp.category = category
            mock_disp.subcategory = "Test Sub"
            mock_disp.display_name = f"{category} Disposition"
            mock_disp.color_hex = "#00FF00"
            mock_disp.color_name = "green"
            mock_disp.priority_score = 5
            mock_disp.description = "Test description"
            mock_disp.requires_escalation = False
            mock_disp.is_system = True
            mock_disp.created_at = datetime.now(UTC)
            mock_disp.updated_at = datetime.now(UTC)
            return mock_disp

        grouped_data = {
            "Benign": [create_mock_disposition("Benign")],
            "Suspicious": [create_mock_disposition("Suspicious")],
            "Malicious": [create_mock_disposition("Malicious")],
        }
        mock_disposition_repo.get_by_category.return_value = grouped_data

        # Act
        result = await disposition_service.get_by_category()

        # Assert
        assert "Benign" in result
        assert "Suspicious" in result
        assert "Malicious" in result
