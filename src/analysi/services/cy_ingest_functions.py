"""
Cy Native Functions for Alert Ingestion and Checkpoint Management.

Project Symi: Platform Cy functions for scheduled alert ingestion tasks.
Provides ingest_alerts(), get_checkpoint(), set_checkpoint(), and default_lookback().

Pattern follows cy_alert_functions.py and cy_task_functions.py:
1. CyIngestFunctions class holds session/tenant/context
2. create_cy_ingest_functions() factory returns dict of callables
3. Registered in DefaultTaskExecutor._load_ingest_functions()
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.repositories.checkpoint_repository import CheckpointRepository
from analysi.repositories.control_event_repository import ControlEventRepository

logger = get_logger(__name__)

# Default lookback period in hours (configurable via env var)
DEFAULT_LOOKBACK_HOURS = 2


class CyIngestFunctions:
    """Platform Cy functions for alert ingestion and checkpoint management."""

    def __init__(
        self, session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.execution_context = execution_context
        self.checkpoint_repo = CheckpointRepository(session)
        self.control_event_repo = ControlEventRepository(session)

        # Parse task_id from execution_context (stored as string UUID)
        raw_task_id = execution_context.get("task_id")
        self.task_id: UUID | None = UUID(raw_task_id) if raw_task_id else None

        # Build AlertService for ingest_alerts (lazy — only if integration_id present)
        self.alert_service: Any = None
        if execution_context.get("integration_id"):
            self._init_alert_service()

    def _init_alert_service(self) -> None:
        """Initialize AlertService for alert ingestion."""
        from analysi.repositories.alert_repository import (
            AlertAnalysisRepository,
            AlertRepository,
            DispositionRepository,
        )
        from analysi.services.alert_service import AlertService

        alert_repo = AlertRepository(self.session)
        analysis_repo = AlertAnalysisRepository(self.session)
        disposition_repo = DispositionRepository(self.session)
        self.alert_service = AlertService(
            alert_repo=alert_repo,
            analysis_repo=analysis_repo,
            disposition_repo=disposition_repo,
            session=self.session,
        )

    async def ingest_alerts(self, alerts: list[dict]) -> dict:
        """Persist OCSF-formatted alerts and emit control events.

        Delegates to AlertService.create_alert() for each alert. Emits an
        "alert:ingested" control event for each successfully created alert.

        Args:
            alerts: List of OCSF-formatted alert dicts (already normalized).

        Returns:
            {"created": int, "duplicates": int, "errors": int}

        Raises:
            TypeError: If alerts is not a list.
        """
        if not isinstance(alerts, list):
            raise TypeError(
                f"ingest_alerts expects a list of dicts, got {type(alerts).__name__}"
            )

        if not self.alert_service:
            raise RuntimeError(
                "ingest_alerts requires integration_id in execution_context"
            )

        if not alerts:
            return {"created": 0, "duplicates": 0, "errors": 0}

        from analysi.integrations.framework.alert_ingest import AlertIngestionService

        created = 0
        duplicates = 0
        errors = 0

        for ocsf_alert in alerts:
            try:
                # Convert OCSF dict to AlertCreate schema
                alert_create = AlertIngestionService._ocsf_to_alert_create(ocsf_alert)

                # Persist via AlertService
                alert_response = await self.alert_service.create_alert(
                    self.tenant_id, alert_create
                )
                created += 1

                # Emit control event for the new alert
                await self.control_event_repo.insert(
                    tenant_id=self.tenant_id,
                    channel="alert:ingested",
                    payload={"alert_id": str(alert_response.alert_id)},
                )

            except ValueError as e:
                if "Duplicate alert detected" in str(e):
                    duplicates += 1
                else:
                    logger.error(
                        "ingest_alerts_value_error",
                        error=str(e),
                        tenant_id=self.tenant_id,
                    )
                    errors += 1
            except Exception as e:
                logger.error(
                    "ingest_alerts_error",
                    error=str(e),
                    tenant_id=self.tenant_id,
                )
                errors += 1

        logger.info(
            "ingest_alerts_complete",
            tenant_id=self.tenant_id,
            created=created,
            duplicates=duplicates,
            errors=errors,
        )

        return {"created": created, "duplicates": duplicates, "errors": errors}

    async def get_checkpoint(self, key: str) -> Any | None:
        """Read a checkpoint value scoped to (tenant_id, task_id, key).

        Returns None if no checkpoint exists.

        Raises:
            ValueError: If task_id is not available in execution_context.
        """
        if not self.task_id:
            raise ValueError("get_checkpoint requires task_id in execution_context")

        return await self.checkpoint_repo.get(self.tenant_id, self.task_id, key)

    async def set_checkpoint(self, key: str, value: Any) -> None:
        """Write a checkpoint value scoped to (tenant_id, task_id, key).

        Uses UPSERT -- creates or updates. Flushes but does not commit
        (commit happens at task completion).

        Raises:
            ValueError: If task_id is not available in execution_context.
        """
        if not self.task_id:
            raise ValueError("set_checkpoint requires task_id in execution_context")

        await self.checkpoint_repo.upsert(self.tenant_id, self.task_id, key, value)

        logger.debug(
            "checkpoint_set",
            tenant_id=self.tenant_id,
            task_id=str(self.task_id),
            key=key,
        )

    def default_lookback(self) -> datetime:
        """Return a configurable lookback time (default: now - 2 hours).

        Reads ANALYSI_DEFAULT_LOOKBACK_HOURS env var.
        Returns timezone-aware UTC datetime.
        """
        hours = int(
            os.environ.get("ANALYSI_DEFAULT_LOOKBACK_HOURS", DEFAULT_LOOKBACK_HOURS)
        )
        return datetime.now(UTC) - timedelta(hours=hours)


def create_cy_ingest_functions(
    session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
) -> dict[str, Any]:
    """Create dictionary of ingest/checkpoint functions for Cy interpreter.

    Checkpoint functions (get_checkpoint, set_checkpoint) and default_lookback
    are always available. ingest_alerts is only included when integration_id
    is present in execution_context.

    Args:
        session: Database session for DB operations.
        tenant_id: Tenant identifier for scoping.
        execution_context: Task execution context.

    Returns:
        Dictionary mapping function names to callables.
    """
    ingest_funcs = CyIngestFunctions(session, tenant_id, execution_context)

    # Checkpoint and lookback wrappers (always available)
    async def get_checkpoint_wrapper(key: str) -> Any | None:
        """Cy-compatible wrapper for get_checkpoint."""
        return await ingest_funcs.get_checkpoint(key)

    async def set_checkpoint_wrapper(key: str, value: Any) -> None:
        """Cy-compatible wrapper for set_checkpoint."""
        await ingest_funcs.set_checkpoint(key, value)

    def default_lookback_wrapper() -> datetime:
        """Cy-compatible wrapper for default_lookback."""
        return ingest_funcs.default_lookback()

    functions: dict[str, Any] = {
        "get_checkpoint": get_checkpoint_wrapper,
        "set_checkpoint": set_checkpoint_wrapper,
        "default_lookback": default_lookback_wrapper,
    }

    # ingest_alerts only available when integration_id is set
    if execution_context.get("integration_id"):

        async def ingest_alerts_wrapper(alerts: list[dict]) -> dict:
            """Cy-compatible wrapper for ingest_alerts."""
            return await ingest_funcs.ingest_alerts(alerts)

        functions["ingest_alerts"] = ingest_alerts_wrapper

    return functions
