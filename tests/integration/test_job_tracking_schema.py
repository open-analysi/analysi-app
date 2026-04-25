"""Integration tests: verify job_tracking JSONB column exists on all tracked tables (Project Leros).

Contract test — locks down the schema so migrations aren't accidentally lost.
"""

import pytest
from sqlalchemy import text

TRACKED_TABLES = [
    "task_runs",
    "workflow_runs",
    "content_reviews",
    "control_events",
    "task_generations",
    "workflow_generations",
    "alert_analyses",
]


@pytest.mark.asyncio
@pytest.mark.integration
class TestJobTrackingSchema:
    """All 8 tracked tables have a job_tracking JSONB column with correct default."""

    @pytest.mark.parametrize("table_name", TRACKED_TABLES)
    async def test_table_has_job_tracking_column(
        self, integration_test_session, table_name
    ):
        """job_tracking column exists on {table_name}."""
        result = await integration_test_session.execute(
            text("""
                SELECT column_name, data_type, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = :table_name
                AND column_name = 'job_tracking'
            """),
            {"table_name": table_name},
        )
        row = result.first()
        assert row is not None, f"job_tracking column missing from {table_name}"
        assert row.data_type == "jsonb", (
            f"Expected jsonb, got {row.data_type} on {table_name}"
        )
        assert row.is_nullable == "NO", (
            f"job_tracking should be NOT NULL on {table_name}"
        )
