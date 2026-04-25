"""Unit tests for Cy Ingest Functions."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.services.cy_ingest_functions import (
    CyIngestFunctions,
    create_cy_ingest_functions,
)


class TestCyIngestFunctions:
    """Unit tests for CyIngestFunctions class."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def task_id(self):
        return str(uuid4())

    @pytest.fixture
    def execution_context(self, task_id):
        return {
            "task_id": task_id,
            "tenant_id": "test-tenant",
            "session": AsyncMock(spec=AsyncSession),
        }

    @pytest.fixture
    def execution_context_with_integration(self, execution_context):
        ctx = dict(execution_context)
        ctx["integration_id"] = str(uuid4())
        return ctx

    @pytest.fixture
    def ingest_functions(self, mock_session, execution_context):
        return CyIngestFunctions(
            session=mock_session,
            tenant_id="test-tenant",
            execution_context=execution_context,
        )

    @pytest.fixture
    def ingest_functions_with_integration(
        self, mock_session, execution_context_with_integration
    ):
        return CyIngestFunctions(
            session=mock_session,
            tenant_id="test-tenant",
            execution_context=execution_context_with_integration,
        )

    # ── get_checkpoint tests ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_checkpoint_returns_value(self, ingest_functions, mock_session):
        """get_checkpoint returns stored JSONB value."""
        # Mock the checkpoint repository's get method
        ingest_functions.checkpoint_repo = AsyncMock()
        ingest_functions.checkpoint_repo.get.return_value = {
            "ts": "2026-03-27T10:00:00Z"
        }

        result = await ingest_functions.get_checkpoint("last_pull")

        assert result == {"ts": "2026-03-27T10:00:00Z"}
        ingest_functions.checkpoint_repo.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_checkpoint_returns_none_for_missing(self, ingest_functions):
        """get_checkpoint returns None when key not found."""
        ingest_functions.checkpoint_repo = AsyncMock()
        ingest_functions.checkpoint_repo.get.return_value = None

        result = await ingest_functions.get_checkpoint("nonexistent")

        assert result is None

    # ── set_checkpoint tests ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_set_checkpoint_upserts_value(self, ingest_functions, task_id):
        """set_checkpoint calls repo upsert with correct args."""
        ingest_functions.checkpoint_repo = AsyncMock()
        mock_checkpoint = MagicMock()
        ingest_functions.checkpoint_repo.upsert.return_value = mock_checkpoint

        await ingest_functions.set_checkpoint("last_pull", "2026-03-27T12:00:00Z")

        ingest_functions.checkpoint_repo.upsert.assert_called_once_with(
            "test-tenant",
            ingest_functions.task_id,
            "last_pull",
            "2026-03-27T12:00:00Z",
        )

    # ── default_lookback tests ────────────────────────────────────

    def test_default_lookback_returns_utc_datetime(self, ingest_functions):
        """default_lookback returns timezone-aware UTC datetime."""
        result = ingest_functions.default_lookback()

        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_default_lookback_default_two_hours(self, ingest_functions):
        """Without env var, returns approximately now - 2 hours."""
        before = datetime.now(UTC) - timedelta(hours=2, seconds=5)
        result = ingest_functions.default_lookback()
        after = datetime.now(UTC) - timedelta(hours=2)

        # Result should be within a few seconds of now - 2 hours
        assert before <= result <= after + timedelta(seconds=5)

    def test_default_lookback_respects_env_var(self, ingest_functions):
        """Reads ANALYSI_DEFAULT_LOOKBACK_HOURS env var."""
        with patch.dict(os.environ, {"ANALYSI_DEFAULT_LOOKBACK_HOURS": "6"}):
            before = datetime.now(UTC) - timedelta(hours=6, seconds=5)
            result = ingest_functions.default_lookback()
            after = datetime.now(UTC) - timedelta(hours=6)

            assert before <= result <= after + timedelta(seconds=5)

    # ── ingest_alerts tests ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_ingest_alerts_handles_empty_list(
        self, ingest_functions_with_integration
    ):
        """Empty list returns {created: 0, duplicates: 0, errors: 0}."""
        result = await ingest_functions_with_integration.ingest_alerts([])

        assert result == {"created": 0, "duplicates": 0, "errors": 0}

    @pytest.mark.asyncio
    async def test_ingest_alerts_persists_and_returns_counts(
        self, ingest_functions_with_integration, mock_session
    ):
        """ingest_alerts creates alerts and returns created/duplicates/errors counts."""
        # Mock the alert service
        mock_alert = MagicMock()
        mock_alert.alert_id = uuid4()
        mock_alert.id = mock_alert.alert_id

        ingest_functions_with_integration.alert_service = AsyncMock()
        ingest_functions_with_integration.alert_service.create_alert = AsyncMock(
            return_value=mock_alert
        )
        ingest_functions_with_integration.control_event_repo = AsyncMock()

        alerts = [
            {
                "message": "Test Alert 1",
                "severity_id": 4,
                "time_dt": datetime.now(UTC).isoformat(),
                "metadata": {"product": {"vendor_name": "Test", "name": "TestProd"}},
                "finding_info": {"title": "Test"},
                "raw_data": '{"test": "data"}',
            }
        ]

        result = await ingest_functions_with_integration.ingest_alerts(alerts)

        assert result["created"] == 1
        assert result["duplicates"] == 0
        assert result["errors"] == 0
        ingest_functions_with_integration.alert_service.create_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_alerts_emits_control_events(
        self, ingest_functions_with_integration
    ):
        """Each created alert gets an alert:ingested control event."""
        mock_alert = MagicMock()
        mock_alert.alert_id = uuid4()
        mock_alert.id = mock_alert.alert_id

        ingest_functions_with_integration.alert_service = AsyncMock()
        ingest_functions_with_integration.alert_service.create_alert = AsyncMock(
            return_value=mock_alert
        )
        ingest_functions_with_integration.control_event_repo = AsyncMock()

        alerts = [
            {
                "message": "Test Alert",
                "severity_id": 3,
                "time_dt": datetime.now(UTC).isoformat(),
                "metadata": {"product": {"vendor_name": "V", "name": "P"}},
                "finding_info": {},
                "raw_data": '{"test": "data"}',
            }
        ]

        await ingest_functions_with_integration.ingest_alerts(alerts)

        ingest_functions_with_integration.control_event_repo.insert.assert_called_once_with(
            tenant_id="test-tenant",
            channel="alert:ingested",
            payload={"alert_id": str(mock_alert.alert_id)},
        )

    @pytest.mark.asyncio
    async def test_ingest_alerts_handles_duplicates(
        self, ingest_functions_with_integration
    ):
        """Duplicate alerts counted, no control event emitted for them."""
        ingest_functions_with_integration.alert_service = AsyncMock()
        ingest_functions_with_integration.alert_service.create_alert = AsyncMock(
            side_effect=ValueError("Duplicate alert detected")
        )
        ingest_functions_with_integration.control_event_repo = AsyncMock()

        alerts = [
            {
                "message": "Dup Alert",
                "severity_id": 3,
                "time_dt": datetime.now(UTC).isoformat(),
                "metadata": {"product": {"vendor_name": "V", "name": "P"}},
                "finding_info": {},
                "raw_data": '{"dup": "data"}',
            }
        ]

        result = await ingest_functions_with_integration.ingest_alerts(alerts)

        assert result["duplicates"] == 1
        assert result["created"] == 0
        ingest_functions_with_integration.control_event_repo.insert.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_alerts_handles_errors_gracefully(
        self, ingest_functions_with_integration
    ):
        """Individual alert errors don't stop batch processing."""
        mock_alert = MagicMock()
        mock_alert.alert_id = uuid4()
        mock_alert.id = mock_alert.alert_id

        ingest_functions_with_integration.alert_service = AsyncMock()
        # First call raises non-duplicate error, second succeeds
        ingest_functions_with_integration.alert_service.create_alert = AsyncMock(
            side_effect=[RuntimeError("DB error"), mock_alert]
        )
        ingest_functions_with_integration.control_event_repo = AsyncMock()

        alerts = [
            {
                "message": "Bad Alert",
                "severity_id": 3,
                "time_dt": datetime.now(UTC).isoformat(),
                "metadata": {"product": {"vendor_name": "V", "name": "P"}},
                "finding_info": {},
                "raw_data": '{"bad": "data"}',
            },
            {
                "message": "Good Alert",
                "severity_id": 4,
                "time_dt": datetime.now(UTC).isoformat(),
                "metadata": {"product": {"vendor_name": "V", "name": "P"}},
                "finding_info": {},
                "raw_data": '{"good": "data"}',
            },
        ]

        result = await ingest_functions_with_integration.ingest_alerts(alerts)

        assert result["created"] == 1
        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_ingest_alerts_rejects_non_list_input(
        self, ingest_functions_with_integration
    ):
        """Raises TypeError for non-list input."""
        with pytest.raises(TypeError):
            await ingest_functions_with_integration.ingest_alerts("not a list")

    # ── Context requirement tests ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_checkpoint_requires_task_id(self, mock_session):
        """Raises ValueError if task_id missing from execution_context."""
        ctx = {"tenant_id": "test-tenant"}  # No task_id
        funcs = CyIngestFunctions(mock_session, "test-tenant", ctx)

        with pytest.raises(ValueError, match="task_id"):
            await funcs.get_checkpoint("key")

    @pytest.mark.asyncio
    async def test_set_checkpoint_requires_task_id(self, mock_session):
        """Raises ValueError if task_id missing from execution_context."""
        ctx = {"tenant_id": "test-tenant"}  # No task_id
        funcs = CyIngestFunctions(mock_session, "test-tenant", ctx)

        with pytest.raises(ValueError, match="task_id"):
            await funcs.set_checkpoint("key", "value")


class TestCreateCyIngestFunctions:
    """Test the factory function."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    def test_factory_returns_all_functions_with_integration_id(self, mock_session):
        """Factory includes ingest_alerts when integration_id is set."""
        ctx = {
            "task_id": str(uuid4()),
            "tenant_id": "test-tenant",
            "integration_id": str(uuid4()),
        }
        funcs = create_cy_ingest_functions(mock_session, "test-tenant", ctx)

        assert "ingest_alerts" in funcs
        assert "get_checkpoint" in funcs
        assert "set_checkpoint" in funcs
        assert "default_lookback" in funcs
        assert all(callable(v) for v in funcs.values())

    def test_factory_excludes_ingest_alerts_without_integration_id(self, mock_session):
        """Factory omits ingest_alerts when no integration_id."""
        ctx = {
            "task_id": str(uuid4()),
            "tenant_id": "test-tenant",
        }
        funcs = create_cy_ingest_functions(mock_session, "test-tenant", ctx)

        assert "ingest_alerts" not in funcs
        assert "get_checkpoint" in funcs
        assert "set_checkpoint" in funcs
        assert "default_lookback" in funcs

    def test_factory_always_includes_checkpoint_functions(self, mock_session):
        """get/set_checkpoint and default_lookback always present regardless of integration_id."""
        ctx = {
            "task_id": str(uuid4()),
            "tenant_id": "test-tenant",
        }
        funcs = create_cy_ingest_functions(mock_session, "test-tenant", ctx)

        assert "get_checkpoint" in funcs
        assert "set_checkpoint" in funcs
        assert "default_lookback" in funcs
