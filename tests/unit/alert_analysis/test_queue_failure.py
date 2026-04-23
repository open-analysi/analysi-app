"""Tests for Issue #5: Queue failure handling in alert router.

Bug: If queue_alert_analysis raises a non-ImportError (e.g., Redis ConnectionError),
the exception is NOT caught, but db.commit() at the end of the endpoint is still
reached because the exception propagates outside the try/except block.
This can leave analysis records in an inconsistent state.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _mock_request():
    """Create a mock Request with request_id for api_response()."""
    req = MagicMock()
    req.state.request_id = "test-request-id"
    return req


class TestQueueFailureHandling:
    """Test that Redis/queue failures are handled properly in the router."""

    @pytest.mark.asyncio
    async def test_redis_failure_returns_503(self):
        """ConnectionError from queue_alert_analysis should return 503, not 500."""

        # We test the router logic directly via mock
        mock_analysis = AsyncMock()
        mock_analysis.id = uuid4()
        mock_analysis.status = "running"

        mock_analysis_service = AsyncMock()
        mock_analysis_service.start_analysis.return_value = mock_analysis

        mock_db = AsyncMock()

        # Mock queue_alert_analysis to raise ConnectionError
        with patch(
            "analysi.routers.alerts.AlertAnalysisService",
            return_value=mock_analysis_service,
        ):
            with patch(
                "analysi.alert_analysis.worker.queue_alert_analysis",
                side_effect=ConnectionError("Redis connection refused"),
            ):
                from fastapi import HTTPException

                from analysi.routers.alerts import start_alert_analysis

                alert_id = uuid4()
                tenant = "test-tenant"

                # The endpoint should catch the ConnectionError and raise 503
                with pytest.raises(HTTPException) as exc_info:
                    await start_alert_analysis(
                        alert_id=alert_id,
                        request=_mock_request(),
                        tenant=tenant,
                        db=mock_db,
                    )

                assert exc_info.value.status_code == 503, (
                    f"Expected 503 for queue failure, got {exc_info.value.status_code}"
                )

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_commit(self):
        """When queue fails, db.commit() should NOT be called."""
        mock_analysis = AsyncMock()
        mock_analysis.id = uuid4()
        mock_analysis.status = "running"

        mock_analysis_service = AsyncMock()
        mock_analysis_service.start_analysis.return_value = mock_analysis

        mock_db = AsyncMock()

        with patch(
            "analysi.routers.alerts.AlertAnalysisService",
            return_value=mock_analysis_service,
        ):
            with patch(
                "analysi.alert_analysis.worker.queue_alert_analysis",
                side_effect=ConnectionError("Redis connection refused"),
            ):
                from analysi.routers.alerts import start_alert_analysis

                alert_id = uuid4()
                tenant = "test-tenant"

                with contextlib.suppress(Exception):
                    await start_alert_analysis(
                        alert_id=alert_id,
                        request=_mock_request(),
                        tenant=tenant,
                        db=mock_db,
                    )

                # db.commit() should NOT have been called
                mock_db.commit.assert_not_called()
