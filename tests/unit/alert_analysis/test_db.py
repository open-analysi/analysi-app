"""Unit tests for AlertAnalysisDB."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.alert_analysis.db import AlertAnalysisDB


class TestAlertAnalysisDB:
    """Test AlertAnalysisDB alert data retrieval."""

    @pytest.fixture
    def mock_session(self):
        """Mock async database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def alert_db(self, mock_session):
        """AlertAnalysisDB instance with mocked session."""
        db = AlertAnalysisDB(session=mock_session)
        return db

    @pytest.mark.asyncio
    async def test_get_alert_returns_rule_name(self, alert_db, mock_session):
        """Test get_alert returns rule_name field required by WorkflowBuilderStep.

        WorkflowBuilderStep._get_analysis_group_title() requires
        rule_name field from alert data. This test ensures db.get_alert()
        includes this field in the returned dictionary.
        """
        # Arrange
        from analysi.models.alert import Alert

        alert_id = uuid4()
        expected_rule_name = "Suspicious Login Activity"

        mock_alert = MagicMock(spec=Alert)
        mock_alert.id = alert_id
        mock_alert.tenant_id = "test-tenant"
        mock_alert.title = "Test Alert"
        mock_alert.rule_name = expected_rule_name
        mock_alert.severity = "high"
        mock_alert.severity_id = 4
        mock_alert.raw_data = '{"test": "data"}'
        mock_alert.raw_data_hash = "abc123"
        mock_alert.source_vendor = None
        mock_alert.source_product = None
        mock_alert.source_event_id = None
        mock_alert.finding_info = {}
        mock_alert.ocsf_metadata = {}
        mock_alert.evidences = None
        mock_alert.observables = None
        mock_alert.osint = None
        mock_alert.actor = None
        mock_alert.device = None
        mock_alert.cloud = None
        mock_alert.vulnerabilities = None
        mock_alert.unmapped = None
        mock_alert.detected_at = None
        mock_alert.triggering_event_time = None

        # Mock query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert
        mock_session.execute.return_value = mock_result

        # Act
        result = await alert_db.get_alert(str(alert_id))

        # Assert
        assert result is not None
        assert "rule_name" in result, "rule_name field missing from alert data"
        assert result["rule_name"] == expected_rule_name
        assert result["alert_id"] == str(alert_id)
        assert result["tenant_id"] == "test-tenant"
        assert result["title"] == "Test Alert"
        assert result["severity"] == "high"

    @pytest.mark.asyncio
    async def test_get_alert_returns_triggering_event_time(
        self, alert_db, mock_session
    ):
        """Test get_alert returns triggering_event_time required by AlertBase validation.

        Workflow generation validates alert data against AlertBase schema
        which requires triggering_event_time as a required field.
        """
        # Arrange

        from analysi.models.alert import Alert

        alert_id = uuid4()
        expected_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        mock_alert = MagicMock(spec=Alert)
        mock_alert.id = alert_id
        mock_alert.tenant_id = "test-tenant"
        mock_alert.title = "Test Alert"
        mock_alert.triggering_event_time = expected_time
        mock_alert.severity = "high"
        mock_alert.severity_id = 4
        mock_alert.raw_data = '{"event": "test"}'
        mock_alert.raw_data_hash = "hash123"
        mock_alert.finding_info = {}
        mock_alert.ocsf_metadata = {}
        # Set all other fields that get_alert returns
        for field in [
            "rule_name",
            "source_vendor",
            "source_product",
            "source_event_id",
            "evidences",
            "observables",
            "osint",
            "actor",
            "device",
            "cloud",
            "vulnerabilities",
            "unmapped",
            "detected_at",
        ]:
            setattr(mock_alert, field, None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert
        mock_session.execute.return_value = mock_result

        # Act
        result = await alert_db.get_alert(str(alert_id))

        # Assert
        assert result is not None
        assert "triggering_event_time" in result, (
            "triggering_event_time field missing from alert data"
        )
        assert result["triggering_event_time"] == expected_time.isoformat()

    @pytest.mark.asyncio
    async def test_get_alert_returns_all_alertbase_required_fields(
        self, alert_db, mock_session
    ):
        """Test get_alert returns all AlertBase required fields comprehensively.

        db.get_alert() returns ALL AlertBase fields to prevent missing-field errors.
        """
        # Arrange

        from analysi.models.alert import Alert

        alert_id = uuid4()
        triggering_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)

        mock_alert = MagicMock(spec=Alert)
        mock_alert.id = alert_id
        mock_alert.tenant_id = "test-tenant"
        mock_alert.title = "Comprehensive Test Alert"
        mock_alert.triggering_event_time = triggering_time
        mock_alert.severity = "critical"
        mock_alert.severity_id = 5
        mock_alert.raw_data = '{"comprehensive": "data"}'
        mock_alert.raw_data_hash = "hash456"
        mock_alert.rule_name = "Test Rule"
        mock_alert.finding_info = {"title": "malware"}
        mock_alert.ocsf_metadata = {}
        # Set all optional fields
        for field in [
            "source_vendor",
            "source_product",
            "source_event_id",
            "evidences",
            "observables",
            "osint",
            "actor",
            "device",
            "cloud",
            "vulnerabilities",
            "unmapped",
            "detected_at",
        ]:
            setattr(mock_alert, field, None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert
        mock_session.execute.return_value = mock_result

        # Act
        result = await alert_db.get_alert(str(alert_id))

        # Assert - verify core required fields present
        core_required_fields = [
            "title",
            "triggering_event_time",
            "severity",
            "raw_data",
        ]
        for field in core_required_fields:
            assert field in result, f"Missing core required field: {field}"

        # Assert - verify OCSF fields also present (comprehensive fix)
        ocsf_fields = [
            "rule_name",
            "source_vendor",
            "source_product",
            "finding_info",
            "metadata",
            "observables",
            "actor",
            "device",
            "cloud",
        ]
        for field in ocsf_fields:
            assert field in result, f"Missing OCSF field: {field}"

    @pytest.mark.asyncio
    async def test_get_alert_returns_json_serializable_data(
        self, alert_db, mock_session
    ):
        """get_alert output is passed to httpx json= which calls json.dumps().

        datetime and UUID objects cause 'Object of type datetime is not JSON
        serializable'. All values must be JSON-safe (strings, numbers, None,
        dicts, lists).
        """
        import json

        from analysi.models.alert import Alert

        alert_id = uuid4()
        mock_alert = MagicMock(spec=Alert)
        mock_alert.id = alert_id
        mock_alert.tenant_id = "test-tenant"
        mock_alert.title = "Test Alert"
        mock_alert.triggering_event_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_alert.severity = "high"
        mock_alert.severity_id = 4
        mock_alert.raw_data = '{"event": "test"}'
        mock_alert.raw_data_hash = "hash789"
        mock_alert.detected_at = datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_alert.finding_info = {}
        mock_alert.ocsf_metadata = {}
        # Set remaining optional fields to None
        for field in [
            "rule_name",
            "source_vendor",
            "source_product",
            "source_event_id",
            "evidences",
            "observables",
            "osint",
            "actor",
            "device",
            "cloud",
            "vulnerabilities",
            "unmapped",
        ]:
            setattr(mock_alert, field, None)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert
        mock_session.execute.return_value = mock_result

        result = await alert_db.get_alert(str(alert_id))

        # This is the exact operation that fails in production
        json.dumps(result)  # Must not raise TypeError

        # Datetime fields must be ISO strings, not raw datetime objects
        assert isinstance(result["triggering_event_time"], str)
        assert isinstance(result["detected_at"], str)

    @pytest.mark.asyncio
    async def test_get_alert_returns_empty_dict_when_not_found(
        self, alert_db, mock_session
    ):
        """Test get_alert returns empty dict when alert doesn't exist."""
        # Arrange
        alert_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act
        result = await alert_db.get_alert(str(alert_id))

        # Assert
        assert result == {}


class TestAlertAnalysisDBAdditional:
    """Additional tests for uncovered AlertAnalysisDB methods."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def alert_db(self, mock_session):
        return AlertAnalysisDB(session=mock_session)

    # -----------------------------------------------------------------------
    # get_alert - edge cases
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_alert_returns_empty_when_no_session(self):
        db = AlertAnalysisDB(session=None)
        result = await db.get_alert(str(uuid4()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_alert_returns_empty_on_exception(self, alert_db, mock_session):
        mock_session.execute.side_effect = RuntimeError("DB connection failed")
        result = await alert_db.get_alert(str(uuid4()))
        assert result == {}

    # -----------------------------------------------------------------------
    # get_analysis
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_analysis_returns_empty_when_no_session(self):
        db = AlertAnalysisDB(session=None)
        result = await db.get_analysis(str(uuid4()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_analysis_returns_empty_when_not_found(
        self, alert_db, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await alert_db.get_analysis(str(uuid4()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_analysis_returns_dict_when_found(self, alert_db, mock_session):
        from analysi.models.alert import AlertAnalysis

        analysis_id = uuid4()
        alert_id = uuid4()
        mock_analysis = MagicMock(spec=AlertAnalysis)
        mock_analysis.id = analysis_id
        mock_analysis.alert_id = alert_id
        mock_analysis.status = "running"
        mock_analysis.current_step = "context"
        mock_analysis.steps_progress = {"context": "in_progress"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result

        result = await alert_db.get_analysis(str(analysis_id))
        assert result["id"] == str(analysis_id)
        assert result["alert_id"] == str(alert_id)
        assert result["status"] == "running"
        assert result["current_step"] == "context"

    @pytest.mark.asyncio
    async def test_get_analysis_returns_empty_on_exception(
        self, alert_db, mock_session
    ):
        mock_session.execute.side_effect = RuntimeError("DB error")
        result = await alert_db.get_analysis(str(uuid4()))
        assert result == {}

    # -----------------------------------------------------------------------
    # update_analysis_status
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_analysis_status_no_session(self):
        db = AlertAnalysisDB(session=None)
        # Should return without raising
        await db.update_analysis_status(str(uuid4()), "running")

    @pytest.mark.asyncio
    async def test_update_analysis_status_completed(self, alert_db, mock_session):
        mock_session.execute.return_value = MagicMock()
        mock_session.commit = AsyncMock()
        await alert_db.update_analysis_status(str(uuid4()), "completed")
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_analysis_status_failed(self, alert_db, mock_session):
        mock_session.execute.return_value = MagicMock()
        mock_session.commit = AsyncMock()
        await alert_db.update_analysis_status(
            str(uuid4()), "failed", error="Something went wrong"
        )
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_analysis_status_raises_on_exception(
        self, alert_db, mock_session
    ):
        mock_session.execute.side_effect = RuntimeError("DB error")
        mock_session.rollback = AsyncMock()

        with pytest.raises(RuntimeError):
            await alert_db.update_analysis_status(str(uuid4()), "running")
        mock_session.rollback.assert_called_once()

    # -----------------------------------------------------------------------
    # update_step_progress
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_step_progress_no_session(self):
        db = AlertAnalysisDB(session=None)
        await db.update_step_progress(str(uuid4()), "context_generation", True)

    @pytest.mark.asyncio
    async def test_update_step_progress_analysis_not_found(
        self, alert_db, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Should return without error when analysis not found
        await alert_db.update_step_progress(str(uuid4()), "context_generation", True)

    @pytest.mark.asyncio
    async def test_update_step_progress_mark_completed(self, alert_db, mock_session):
        from analysi.models.alert import AlertAnalysis

        analysis_id = uuid4()
        mock_analysis = MagicMock(spec=AlertAnalysis)
        mock_analysis.steps_progress = None
        mock_analysis.current_step = "context_generation"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        await alert_db.update_step_progress(
            str(analysis_id), "context_generation", completed=True
        )
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_step_progress_mark_failed(self, alert_db, mock_session):
        from analysi.models.alert import AlertAnalysis

        analysis_id = uuid4()
        mock_analysis = MagicMock(spec=AlertAnalysis)
        mock_analysis.steps_progress = None
        mock_analysis.current_step = "context_generation"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        await alert_db.update_step_progress(
            str(analysis_id),
            "context_generation",
            completed=False,
            error="Step failed",
        )
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_step_progress_unknown_step(self, alert_db, mock_session):
        """Unknown step names should be handled gracefully."""
        from analysi.models.alert import AlertAnalysis

        analysis_id = uuid4()
        mock_analysis = MagicMock(spec=AlertAnalysis)
        mock_analysis.steps_progress = None
        mock_analysis.current_step = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        # "unknown_step" is not a valid PipelineStep
        await alert_db.update_step_progress(
            str(analysis_id), "unknown_step", completed=True
        )
        mock_session.commit.assert_called_once()

    # -----------------------------------------------------------------------
    # initialize_steps_progress
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_initialize_steps_progress_no_session(self):
        db = AlertAnalysisDB(session=None)
        result = await db.initialize_steps_progress(str(uuid4()))
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_steps_progress_not_found(self, alert_db, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await alert_db.initialize_steps_progress(str(uuid4()))
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_steps_progress_success(self, alert_db, mock_session):
        from analysi.models.alert import AlertAnalysis

        mock_analysis = MagicMock(spec=AlertAnalysis)
        mock_analysis.steps_progress = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_analysis
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        result = await alert_db.initialize_steps_progress(str(uuid4()))
        assert result is True
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_steps_progress_exception_returns_false(
        self, alert_db, mock_session
    ):
        mock_session.execute.side_effect = RuntimeError("DB error")
        mock_session.rollback = AsyncMock()

        result = await alert_db.initialize_steps_progress(str(uuid4()))
        assert result is False

    # -----------------------------------------------------------------------
    # get_step_progress
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_step_progress_no_session(self):
        db = AlertAnalysisDB(session=None)
        result = await db.get_step_progress(str(uuid4()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_step_progress_returns_progress(self, alert_db, mock_session):
        expected = {"context_generation": {"status": "completed"}}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected
        mock_session.execute.return_value = mock_result

        result = await alert_db.get_step_progress(str(uuid4()))
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_step_progress_returns_empty_when_none(
        self, alert_db, mock_session
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await alert_db.get_step_progress(str(uuid4()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_step_progress_returns_empty_on_exception(
        self, alert_db, mock_session
    ):
        mock_session.execute.side_effect = RuntimeError("DB error")
        result = await alert_db.get_step_progress(str(uuid4()))
        assert result == {}

    # -----------------------------------------------------------------------
    # update_current_step
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_current_step_no_session(self):
        db = AlertAnalysisDB(session=None)
        await db.update_current_step(str(uuid4()), "context_generation")

    @pytest.mark.asyncio
    async def test_update_current_step_success(self, alert_db, mock_session):
        mock_session.execute.return_value = MagicMock()
        mock_session.commit = AsyncMock()
        await alert_db.update_current_step(str(uuid4()), "context_generation")
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_current_step_raises_on_exception(
        self, alert_db, mock_session
    ):
        mock_session.execute.side_effect = RuntimeError("DB error")
        mock_session.rollback = AsyncMock()
        with pytest.raises(RuntimeError):
            await alert_db.update_current_step(str(uuid4()), "context_generation")
        mock_session.rollback.assert_called_once()

    # -----------------------------------------------------------------------
    # update_analysis_results
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_analysis_results_no_session(self):
        db = AlertAnalysisDB(session=None)
        await db.update_analysis_results(
            str(uuid4()), str(uuid4()), 85, "short summary", "long summary"
        )

    @pytest.mark.asyncio
    async def test_update_analysis_results_success(self, alert_db, mock_session):
        mock_session.execute.return_value = MagicMock()
        mock_session.commit = AsyncMock()
        await alert_db.update_analysis_results(
            str(uuid4()), str(uuid4()), 85, "short", "long"
        )
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_analysis_results_raises_on_exception(
        self, alert_db, mock_session
    ):
        mock_session.execute.side_effect = RuntimeError("DB error")
        mock_session.rollback = AsyncMock()
        with pytest.raises(RuntimeError):
            await alert_db.update_analysis_results(
                str(uuid4()), str(uuid4()), 50, "short", "long"
            )
        mock_session.rollback.assert_called_once()

    # -----------------------------------------------------------------------
    # update_alert_status
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_alert_status_no_session(self):
        db = AlertAnalysisDB(session=None)
        await db.update_alert_status(str(uuid4()), "completed")

    @pytest.mark.asyncio
    async def test_update_alert_status_success(self, alert_db, mock_session):
        mock_session.execute.return_value = MagicMock()
        mock_session.commit = AsyncMock()
        await alert_db.update_alert_status(str(uuid4()), "completed")
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_alert_status_swallows_exception_and_rolls_back(
        self, alert_db, mock_session
    ):
        """update_alert_status is best-effort: logs error and rolls back, does not raise."""
        mock_session.execute.side_effect = RuntimeError("DB error")
        mock_session.rollback = AsyncMock()
        # Should NOT raise — best-effort pattern
        await alert_db.update_alert_status(str(uuid4()), "completed")
        mock_session.rollback.assert_called_once()

    # -----------------------------------------------------------------------
    # initialize / close
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_close_with_session(self, alert_db, mock_session):
        mock_session.close = AsyncMock()
        await alert_db.close()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_no_session(self):
        db = AlertAnalysisDB(session=None)
        # Should not raise
        await db.close()

    @pytest.mark.asyncio
    async def test_close_with_engine(self):
        """When engine is set, dispose should be called."""
        db = AlertAnalysisDB(session=None)
        mock_engine = AsyncMock()
        db.engine = mock_engine
        await db.close()
        mock_engine.dispose.assert_called_once()
