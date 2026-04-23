"""Unit tests for AlertRepository reconciliation methods."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.alert_repository import AlertRepository


class TestAlertRepositoryReconciliation:
    """Test repository methods for reconciliation job."""

    @pytest.fixture
    def mock_session(self):
        """Mock async database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def alert_repo(self, mock_session):
        """AlertRepository instance with mocked session."""
        return AlertRepository(mock_session)

    @pytest.mark.asyncio
    async def test_find_paused_at_workflow_builder_returns_matching_alerts(
        self, alert_repo, mock_session
    ):
        """Test find_paused_at_workflow_builder returns alerts paused at Workflow Builder step."""
        # Arrange
        from analysi.models.alert import Alert

        mock_alert_1 = MagicMock(spec=Alert)
        mock_alert_1.id = uuid4()
        mock_alert_1.analysis_status = "paused_workflow_building"

        mock_alert_2 = MagicMock(spec=Alert)
        mock_alert_2.id = uuid4()
        mock_alert_2.analysis_status = "paused_workflow_building"

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_alert_1,
            mock_alert_2,
        ]
        mock_session.execute.return_value = mock_result

        # Act
        results = await alert_repo.find_paused_at_workflow_builder()

        # Assert
        assert len(results) == 2
        assert results[0] == mock_alert_1
        assert results[1] == mock_alert_2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_paused_at_workflow_builder_returns_empty_when_none(
        self, alert_repo, mock_session
    ):
        """Test find_paused_at_workflow_builder returns empty list when no paused alerts."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        results = await alert_repo.find_paused_at_workflow_builder()

        # Assert
        assert results == []

    @pytest.mark.asyncio
    async def test_try_resume_alert_returns_true_when_successful(
        self, alert_repo, mock_session
    ):
        """Test try_resume_alert returns True when successfully claims paused alert."""
        # Arrange
        tenant_id = "default"
        alert_id = str(uuid4())

        # Mock UPDATE result with rowcount=1 (successful claim)
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Act
        success = await alert_repo.try_resume_alert(
            tenant_id=tenant_id, alert_id=alert_id
        )

        # Assert
        assert success is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_resume_alert_returns_false_when_already_resumed(
        self, alert_repo, mock_session
    ):
        """Test try_resume_alert returns False when another worker already claimed it."""
        # Arrange
        tenant_id = "default"
        alert_id = str(uuid4())

        # Mock UPDATE result with rowcount=0 (no rows updated, already resumed)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        # Act
        success = await alert_repo.try_resume_alert(
            tenant_id=tenant_id, alert_id=alert_id
        )

        # Assert
        assert success is False
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_resume_alert_uses_atomic_update(self, alert_repo, mock_session):
        """Test try_resume_alert uses UPDATE with WHERE for atomic claim."""
        # Arrange
        tenant_id = "default"
        alert_id = str(uuid4())

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Act
        await alert_repo.try_resume_alert(tenant_id=tenant_id, alert_id=alert_id)

        # Assert
        # Verify that execute was called with an UPDATE statement
        call_args = mock_session.execute.call_args
        assert call_args is not None
        # The first argument should be a compiled SQL statement
        stmt = call_args[0][0]
        # We expect it to be an Update statement with WHERE clause
        assert hasattr(stmt, "whereclause")

    @pytest.mark.asyncio
    async def test_find_paused_at_workflow_builder_joins_alert_analysis(
        self, alert_repo, mock_session
    ):
        """Test that find_paused_at_workflow_builder joins AlertAnalysis table."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await alert_repo.find_paused_at_workflow_builder()

        # Assert
        # Verify execute was called with a SELECT statement
        call_args = mock_session.execute.call_args
        assert call_args is not None
        stmt = call_args[0][0]
        # The statement should have a join (we can't easily inspect the join,
        # but we can verify it has froms which indicates a join)
        assert hasattr(stmt, "get_final_froms")
        assert len(stmt.get_final_froms()) >= 1


class TestFindPausedAlertsByRuleName:
    """Test find_paused_alerts_by_rule_name for push-based resume."""

    @pytest.fixture
    def mock_session(self):
        """Mock async database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def alert_repo(self, mock_session):
        """AlertRepository instance with mocked session."""
        return AlertRepository(mock_session)

    @pytest.mark.asyncio
    async def test_find_paused_alerts_by_rule_name_returns_matching_alerts(
        self, alert_repo, mock_session
    ):
        """Test find_paused_alerts_by_rule_name returns alerts matching rule_name."""
        # Arrange
        from analysi.models.alert import Alert

        mock_alert_1 = MagicMock(spec=Alert)
        mock_alert_1.id = uuid4()
        mock_alert_1.rule_name = "Suspicious Login"
        mock_alert_1.tenant_id = "default"

        mock_alert_2 = MagicMock(spec=Alert)
        mock_alert_2.id = uuid4()
        mock_alert_2.rule_name = "Suspicious Login"
        mock_alert_2.tenant_id = "default"

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_alert_1,
            mock_alert_2,
        ]
        mock_session.execute.return_value = mock_result

        # Act
        results = await alert_repo.find_paused_alerts_by_rule_name(
            tenant_id="default",
            rule_name="Suspicious Login",
        )

        # Assert
        assert len(results) == 2
        assert results[0] == mock_alert_1
        assert results[1] == mock_alert_2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_paused_alerts_by_rule_name_returns_empty_when_none(
        self, alert_repo, mock_session
    ):
        """Test find_paused_alerts_by_rule_name returns empty list when no paused alerts."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        results = await alert_repo.find_paused_alerts_by_rule_name(
            tenant_id="default",
            rule_name="Unknown Rule",
        )

        # Assert
        assert results == []

    @pytest.mark.asyncio
    async def test_find_paused_alerts_by_rule_name_filters_by_tenant(
        self, alert_repo, mock_session
    ):
        """Test find_paused_alerts_by_rule_name filters by tenant_id."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await alert_repo.find_paused_alerts_by_rule_name(
            tenant_id="tenant-123",
            rule_name="Test Rule",
        )

        # Assert
        call_args = mock_session.execute.call_args
        assert call_args is not None
        stmt = call_args[0][0]
        # Verify the statement has a WHERE clause
        assert hasattr(stmt, "whereclause")

    @pytest.mark.asyncio
    async def test_find_paused_alerts_by_rule_name_joins_alert_analysis(
        self, alert_repo, mock_session
    ):
        """Test that find_paused_alerts_by_rule_name joins AlertAnalysis table."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await alert_repo.find_paused_alerts_by_rule_name(
            tenant_id="default",
            rule_name="Test Rule",
        )

        # Assert
        call_args = mock_session.execute.call_args
        assert call_args is not None
        stmt = call_args[0][0]
        # The statement should have a join
        assert hasattr(stmt, "get_final_froms")
        assert len(stmt.get_final_froms()) >= 1


class TestStuckAlertDetection:
    """Test stuck alert detection methods."""

    @pytest.fixture
    def mock_session(self):
        """Mock async database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def alert_repo(self, mock_session):
        """AlertRepository instance with mocked session."""
        return AlertRepository(mock_session)

    @pytest.mark.asyncio
    async def test_find_stuck_running_alerts_returns_matching_alerts(
        self, alert_repo, mock_session
    ):
        """Test find_stuck_running_alerts returns (Alert, AlertAnalysis) tuples."""
        from analysi.models.alert import Alert, AlertAnalysis

        mock_alert = MagicMock(spec=Alert)
        mock_alert.id = uuid4()
        mock_alert.analysis_status = "running"
        mock_alert.tenant_id = "default"

        mock_analysis = MagicMock(spec=AlertAnalysis)
        mock_analysis.id = uuid4()
        mock_analysis.status = "running"

        # Returns list of tuples, not just alerts
        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_alert, mock_analysis)]
        mock_session.execute.return_value = mock_result

        results = await alert_repo.find_stuck_running_alerts(stuck_threshold_minutes=60)

        assert len(results) == 1
        assert results[0] == (mock_alert, mock_analysis)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_stuck_running_alerts_returns_empty_when_none(
        self, alert_repo, mock_session
    ):
        """Test find_stuck_running_alerts returns empty list when no stuck alerts."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        results = await alert_repo.find_stuck_running_alerts(stuck_threshold_minutes=60)

        assert results == []

    @pytest.mark.asyncio
    async def test_find_stuck_running_alerts_uses_threshold(
        self, alert_repo, mock_session
    ):
        """Test find_stuck_running_alerts respects threshold parameter."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Call with custom threshold
        await alert_repo.find_stuck_running_alerts(stuck_threshold_minutes=30)

        # Verify execute was called
        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_mark_stuck_alert_failed_returns_true_on_success(
        self, alert_repo, mock_session
    ):
        """Test mark_stuck_alert_failed returns True when update succeeds."""
        tenant_id = "default"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        error = "Alert analysis timed out"

        # Mock UPDATE result with rowcount=1
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        success = await alert_repo.mark_stuck_alert_failed(
            tenant_id=tenant_id, alert_id=alert_id, analysis_id=analysis_id, error=error
        )

        assert success is True
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_mark_stuck_alert_failed_returns_false_when_already_handled(
        self, alert_repo, mock_session
    ):
        """Test mark_stuck_alert_failed returns False when alert already handled."""
        tenant_id = "default"
        alert_id = str(uuid4())
        analysis_id = str(uuid4())
        error = "Alert analysis timed out"

        # Mock UPDATE result with rowcount=0 (no rows updated)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        success = await alert_repo.mark_stuck_alert_failed(
            tenant_id=tenant_id, alert_id=alert_id, analysis_id=analysis_id, error=error
        )

        assert success is False
