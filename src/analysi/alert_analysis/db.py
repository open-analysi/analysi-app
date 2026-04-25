"""Database access layer for Alert Analysis Service"""

import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from analysi.common.retry_config import database_retry_policy
from analysi.config.logging import get_logger
from analysi.models.alert import Alert, AlertAnalysis
from analysi.schemas.alert import (
    AnalysisStatus,
    PipelineStep,
    PipelineStepsProgress,
)

logger = get_logger(__name__)


class AlertAnalysisDB:
    """
    Database access layer for alert analysis operations.

    This class provides:
    - READ operations: Used by pipeline for reading alert/analysis data
    - WRITE operations: Used as fallback when REST API is unavailable

    Primary status updates go through REST API (BackendAPIClient).
    Direct DB access is the fallback path for reliability.
    """

    def __init__(self, session: AsyncSession | None = None):
        self.session = session
        self.engine = None
        self.async_session_maker: sessionmaker | None = None

    async def initialize(self):
        """Initialize database connection if not provided."""
        if not self.session:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable not set")

            self.engine = create_async_engine(
                database_url,
                echo=False,
                pool_pre_ping=True,
                connect_args={
                    "server_settings": {"jit": "off"},
                    "command_timeout": 60,
                    "prepared_statement_cache_size": 0,
                },
            )
            self.async_session_maker = sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            self.session = self.async_session_maker()

    async def close(self):
        """Close database connection."""
        if self.session:
            await self.session.close()
        if self.engine:
            await self.engine.dispose()

    async def get_alert(self, alert_id: str) -> dict[str, Any]:
        """
        Get alert data from database.
        """
        logger.debug("fetching_alert", alert_id=alert_id)

        if not self.session:
            return {}

        try:
            stmt = select(Alert).where(Alert.id == UUID(alert_id))
            result = await self.session.execute(stmt)
            alert = result.scalar_one_or_none()

            if alert:
                return {
                    # Identifiers (not in AlertBase but needed by pipeline)
                    "alert_id": str(alert.id),
                    "tenant_id": alert.tenant_id,
                    # Core fields
                    "title": alert.title,
                    "triggering_event_time": (
                        alert.triggering_event_time.isoformat()
                        if alert.triggering_event_time
                        else None
                    ),
                    "severity": alert.severity,
                    "severity_id": alert.severity_id,
                    "raw_data": alert.raw_data,
                    "raw_data_hash": alert.raw_data_hash,
                    # Source information
                    "source_vendor": alert.source_vendor,
                    "source_product": alert.source_product,
                    "rule_name": alert.rule_name,
                    "source_event_id": alert.source_event_id,
                    # OCSF structured JSONB fields
                    "finding_info": alert.finding_info,
                    "metadata": alert.ocsf_metadata,
                    "evidences": alert.evidences,
                    "observables": alert.observables,
                    "osint": alert.osint,
                    "actor": alert.actor,
                    "device": alert.device,
                    "cloud": alert.cloud,
                    "vulnerabilities": alert.vulnerabilities,
                    "unmapped": alert.unmapped,
                    # Timestamps
                    "detected_at": (
                        alert.detected_at.isoformat() if alert.detected_at else None
                    ),
                }
        except Exception as e:
            logger.error("error_fetching_alert", error=str(e))

        return {}

    async def get_analysis(self, analysis_id: str) -> dict[str, Any]:
        """
        Get alert analysis record.
        """
        logger.debug("fetching_analysis", analysis_id=analysis_id)

        if not self.session:
            return {}

        try:
            stmt = select(AlertAnalysis).where(AlertAnalysis.id == UUID(analysis_id))
            result = await self.session.execute(stmt)
            analysis = result.scalar_one_or_none()

            if analysis:
                return {
                    "id": str(analysis.id),
                    "alert_id": str(analysis.alert_id),
                    "status": analysis.status,
                    "current_step": analysis.current_step,
                    "steps_progress": analysis.steps_progress or {},
                }
        except Exception as e:
            logger.error("error_fetching_analysis", error=str(e))

        return {}

    @database_retry_policy()
    async def update_analysis_status(
        self, analysis_id: str, status: str, error: str | None = None
    ):
        """
        Update the overall analysis status with automatic retry on DB errors.
        """
        logger.info(
            "updating_analysis_status_to", analysis_id=analysis_id, status=status
        )

        if not self.session:
            return

        try:
            values_to_update = {"status": status, "updated_at": datetime.now(UTC)}

            if status == AnalysisStatus.COMPLETED:
                values_to_update["completed_at"] = datetime.now(UTC)
            elif status == AnalysisStatus.RUNNING and not error:
                values_to_update["started_at"] = datetime.now(UTC)
            elif status == AnalysisStatus.FAILED and error:
                values_to_update["error_message"] = error

            stmt = (
                update(AlertAnalysis)
                .where(AlertAnalysis.id == UUID(analysis_id))
                .values(**values_to_update)
            )

            await self.session.execute(stmt)
            await self.session.commit()
        except Exception as e:
            logger.error("error_updating_analysis_status", error=str(e))
            await self.session.rollback()
            raise

    async def update_step_progress(
        self,
        analysis_id: str,
        step_name: str,
        completed: bool,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ):
        """
        Update progress for a specific step in steps_progress JSONB.

        Uses new PipelineStepsProgress schema format with all 4 steps pre-populated.
        Handles backward compatibility with old format via from_dict().
        """
        logger.info(
            "updating_step_for_analysis", step_name=step_name, analysis_id=analysis_id
        )

        if not self.session:
            return

        try:
            # Get current analysis
            stmt = select(AlertAnalysis).where(AlertAnalysis.id == UUID(analysis_id))
            result_db = await self.session.execute(stmt)
            analysis = result_db.scalar_one_or_none()

            if not analysis:
                return

            # Load existing progress or initialize with new schema
            progress = PipelineStepsProgress.from_dict(analysis.steps_progress or {})

            # Convert step_name to PipelineStep enum
            try:
                pipeline_step = PipelineStep(step_name)
            except ValueError:
                logger.warning(
                    "unknown_step_name_using_raw_update", step_name=step_name
                )
                # Fallback for unknown steps - shouldn't happen in normal operation
                pipeline_step = None

            if pipeline_step:
                if error:
                    progress.mark_step_failed(pipeline_step, error)
                elif completed:
                    progress.mark_step_completed(pipeline_step, result)
                else:
                    # Step started (not completed, no error)
                    progress.mark_step_in_progress(pipeline_step)

            # Save updated progress
            analysis.steps_progress = progress.to_dict()

            # Update current_step field based on step status
            if not completed:
                analysis.current_step = step_name
            elif step_name == analysis.current_step:
                # Clear current_step when the active step completes
                analysis.current_step = None

            await self.session.commit()

        except Exception as e:
            logger.error("error_updating_step_progress", error=str(e))
            await self.session.rollback()
            raise

    async def initialize_steps_progress(self, analysis_id: str) -> bool:
        """
        Initialize steps_progress with all 4 pipeline steps.

        Idempotent: if steps already exist (e.g., from a prior run that was
        resumed after HITL pause), their state is preserved.  Only missing
        steps are added as ``not_started``.

        Returns:
            True if initialization was successful, False otherwise.
        """
        logger.info("initializing_steps_progress_for_analysis", analysis_id=analysis_id)

        if not self.session:
            return False

        try:
            stmt = select(AlertAnalysis).where(AlertAnalysis.id == UUID(analysis_id))
            result = await self.session.execute(stmt)
            analysis = result.scalar_one_or_none()

            if not analysis:
                logger.warning(
                    "analysis_not_found_for_initialization", analysis_id=analysis_id
                )
                return False

            # If progress already has steps (resume / re-queue), preserve them.
            # Check the raw dict for the "steps" key to avoid from_dict({})
            # falling through to initialize_all_steps and masking empty state.
            raw_progress = analysis.steps_progress or {}
            if raw_progress.get("steps"):
                logger.info(
                    "steps_progress_already_initialized",
                    analysis_id=analysis_id,
                    step_count=len(raw_progress["steps"]),
                )
                return True

            # First run — initialize all steps to not_started.
            progress = PipelineStepsProgress.initialize_all_steps()
            analysis.steps_progress = progress.to_dict()

            await self.session.commit()
            logger.info(
                "initialized_steps_progress_for_analysis", analysis_id=analysis_id
            )
            return True

        except Exception as e:
            logger.error("error_initializing_steps_progress", error=str(e))
            await self.session.rollback()
            return False

    async def get_step_progress(self, analysis_id: str) -> dict[str, Any]:
        """
        Get progress for all steps.
        """
        if not self.session:
            return {}

        try:
            stmt = select(AlertAnalysis.steps_progress).where(
                AlertAnalysis.id == UUID(analysis_id)
            )
            result = await self.session.execute(stmt)
            steps_progress = result.scalar_one_or_none()

            return steps_progress or {}
        except Exception as e:
            logger.error("error_getting_step_progress", error=str(e))
            return {}

    async def update_current_step(self, analysis_id: str, step_name: str):
        """
        Update the current_step field.
        """
        logger.info(
            "setting_current_step_to_for_analysis",
            step_name=step_name,
            analysis_id=analysis_id,
        )

        if not self.session:
            return

        try:
            stmt = (
                update(AlertAnalysis)
                .where(AlertAnalysis.id == UUID(analysis_id))
                .values(current_step=step_name, updated_at=datetime.now(UTC))
            )

            await self.session.execute(stmt)
            await self.session.commit()
        except Exception as e:
            logger.error("error_updating_current_step", error=str(e))
            await self.session.rollback()
            raise

    async def update_analysis_results(
        self,
        analysis_id: str,
        disposition_id: str,
        confidence: int,
        short_summary: str,
        long_summary: str,
    ):
        """
        Update analysis with final results.
        """
        logger.info("updating_analysis_with_final_results", analysis_id=analysis_id)

        if not self.session:
            return

        try:
            stmt = (
                update(AlertAnalysis)
                .where(AlertAnalysis.id == UUID(analysis_id))
                .values(
                    disposition_id=UUID(disposition_id) if disposition_id else None,
                    confidence=confidence,
                    short_summary=short_summary,
                    long_summary=long_summary,
                    updated_at=datetime.now(UTC),
                )
            )

            await self.session.execute(stmt)
            await self.session.commit()
        except Exception as e:
            logger.error("error_updating_analysis_results", error=str(e))
            await self.session.rollback()
            raise

    async def update_alert_status(self, alert_id: str, analysis_status: str):
        """
        Update alert's analysis status.
        """
        logger.info(
            "updating_alert_analysisstatus_to",
            alert_id=alert_id,
            analysis_status=analysis_status,
        )

        if not self.session:
            return

        try:
            stmt = (
                update(Alert)
                .where(Alert.id == UUID(alert_id))
                .values(analysis_status=analysis_status, updated_at=datetime.now(UTC))
            )

            await self.session.execute(stmt)
            await self.session.commit()
        except Exception as e:
            logger.error("error_updating_alert_status", error=str(e))
            await self.session.rollback()

    async def update_alert_status_if_current(
        self, alert_id: str, analysis_status: str, analysis_id: str
    ):
        """Update alert status only if the given analysis is still the current one.

        Prevents stale failures from overwriting status when a newer analysis
        (from retry) is already in progress.
        """
        if not self.session:
            return

        try:
            stmt = (
                update(Alert)
                .where(
                    Alert.id == UUID(alert_id),
                    Alert.current_analysis_id == UUID(analysis_id),
                )
                .values(analysis_status=analysis_status, updated_at=datetime.now(UTC))
            )

            result = await self.session.execute(stmt)
            await self.session.commit()

            if result.rowcount == 0:
                logger.info(
                    "skipped_alert_status_update_newer_analysis_active",
                    alert_id=alert_id,
                    stale_analysis_id=analysis_id,
                )
            else:
                logger.info(
                    "updating_alert_analysisstatus_to",
                    alert_id=alert_id,
                    analysis_status=analysis_status,
                )
        except Exception as e:
            logger.error("error_updating_alert_status_if_current", error=str(e))
            await self.session.rollback()
            raise
