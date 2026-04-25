"""Repository for Alert database operations."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, asc, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.schemas.alert import AlertStatus, AnalysisStatus


class AlertRepository:
    """Repository for alert database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_with_deduplication(
        self, tenant_id: str, raw_data_hash: str, **kwargs
    ) -> Alert | None:
        """Create alert with raw_data_hash deduplication."""
        # Check for existing alert with same raw_data_hash
        existing_stmt = select(Alert).where(
            and_(Alert.tenant_id == tenant_id, Alert.raw_data_hash == raw_data_hash)
        )
        result = await self.session.execute(existing_stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return None  # Duplicate found

        # Create new alert
        alert = Alert(tenant_id=tenant_id, raw_data_hash=raw_data_hash, **kwargs)
        self.session.add(alert)
        await self.session.flush()

        return alert

    async def get_next_human_readable_id(self, tenant_id: str) -> str:
        """Generate next sequential human-readable ID atomically."""
        from sqlalchemy import text

        # Use the database function to get and increment the counter atomically
        result = await self.session.execute(
            text("SELECT get_and_increment_alert_id(:tenant_id) as next_id"),
            {"tenant_id": tenant_id},
        )
        next_id = result.scalar()

        return next_id if next_id else Alert.generate_human_readable_id(1)

    async def find_by_filters(
        self,
        tenant_id: str,
        severity: list[str] | None = None,
        status: str | None = None,
        source_vendor: str | None = None,
        source_product: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        disposition_category: str | None = None,
        disposition_subcategory: str | None = None,
        min_confidence: int | None = None,
        max_confidence: int | None = None,
        title_filter: str | None = None,  # Project Rhodes: substring search on title
        ioc_filter: str | None = None,  # Project Rhodes: search by IOC value
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "triggering_event_time",
        sort_order: str = "desc",
    ) -> tuple[list[Alert], int]:
        """Find alerts by various filters with pagination."""
        conditions = [Alert.tenant_id == tenant_id]

        if severity:
            conditions.append(Alert.severity.in_(severity))
        if status:
            conditions.append(Alert.analysis_status == status)
        if source_vendor:
            conditions.append(Alert.source_vendor == source_vendor)
        if source_product:
            conditions.append(Alert.source_product == source_product)
        if title_filter:
            # Split on whitespace so "PowerShell CVE-2022-41082" matches
            # titles containing both words (AND logic on individual terms)
            words = title_filter.strip().split()
            for word in words:
                conditions.append(Alert.title.ilike(f"%{word}%"))
        if ioc_filter:
            # Project Rhodes: search for an IOC value across OCSF JSONB fields.
            # Uses OR logic: match in observables, evidences, or actor JSONB.
            from sqlalchemy import String, cast

            ioc_term = f"%{ioc_filter}%"
            conditions.append(
                or_(
                    cast(Alert.observables, String).ilike(ioc_term),
                    cast(Alert.evidences, String).ilike(ioc_term),
                    cast(Alert.actor, String).ilike(ioc_term),
                )
            )
        if time_from:
            conditions.append(Alert.triggering_event_time >= time_from)
        if time_to:
            conditions.append(Alert.triggering_event_time <= time_to)
        if disposition_category:
            conditions.append(
                Alert.current_disposition_category == disposition_category
            )
        if disposition_subcategory:
            conditions.append(
                Alert.current_disposition_subcategory == disposition_subcategory
            )
        if min_confidence is not None:
            conditions.append(Alert.current_disposition_confidence >= min_confidence)
        if max_confidence is not None:
            conditions.append(Alert.current_disposition_confidence <= max_confidence)

        # Count query
        count_stmt = select(func.count()).select_from(Alert).where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar()

        # Map sort fields to columns
        sort_columns = {
            "human_readable_id": Alert.human_readable_id,
            "title": Alert.title,
            "severity": Alert.severity,
            "analysis_status": Alert.analysis_status,
            "current_disposition_display_name": Alert.current_disposition_display_name,
            "triggering_event_time": Alert.triggering_event_time,
            "created_at": Alert.created_at,
            "updated_at": Alert.updated_at,
        }

        # Get the sort column, default to triggering_event_time if invalid
        sort_column = sort_columns.get(sort_by, Alert.triggering_event_time)

        # Apply sort order
        if sort_order.lower() == "asc":
            order_clause = asc(sort_column)
        else:
            order_clause = desc(sort_column)

        # Data query with pagination
        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(order_clause)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        alerts = result.scalars().all()

        return list(alerts), total

    async def search_similar(
        self, alert_id: UUID, tenant_id: str, threshold: float = 0.7, limit: int = 10
    ) -> list[Alert]:
        """Find similar alerts based on content similarity."""
        # Get the reference alert
        ref_stmt = select(Alert).where(
            and_(Alert.id == alert_id, Alert.tenant_id == tenant_id)
        )
        ref_result = await self.session.execute(ref_stmt)
        ref_alert = ref_result.scalar_one_or_none()

        if not ref_alert:
            return []

        # Simple similarity matching based on OCSF JSONB fields
        # In a real implementation, this would use vector similarity
        from sqlalchemy import String, cast

        conditions = [
            Alert.tenant_id == tenant_id,
            Alert.id != alert_id,
        ]

        # Add similarity conditions using OCSF JSONB text search
        similarity_conditions = []
        if ref_alert.actor:
            # Extract a key value from actor for matching (first non-trivial value)
            for key in ("name", "email_addr", "uid"):
                val = (
                    ref_alert.actor.get(key)
                    if isinstance(ref_alert.actor, dict)
                    else None
                )
                if val:
                    similarity_conditions.append(
                        cast(Alert.actor, String).ilike(f"%{val}%")
                    )
                    break
        if ref_alert.device:
            for key in ("hostname", "name", "ip"):
                val = (
                    ref_alert.device.get(key)
                    if isinstance(ref_alert.device, dict)
                    else None
                )
                if val:
                    similarity_conditions.append(
                        cast(Alert.device, String).ilike(f"%{val}%")
                    )
                    break
        if ref_alert.observables:
            # Pick the first observable value for matching
            for obs in (
                ref_alert.observables if isinstance(ref_alert.observables, list) else []
            ):
                val = obs.get("value") if isinstance(obs, dict) else None
                if val:
                    similarity_conditions.append(
                        cast(Alert.observables, String).ilike(f"%{val}%")
                    )
                    break
        if ref_alert.source_product:
            similarity_conditions.append(
                Alert.source_product == ref_alert.source_product
            )

        if similarity_conditions:
            conditions.append(or_(*similarity_conditions))

        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(desc(Alert.triggering_event_time))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_update_status(
        self, tenant_id: str, alert_ids: list[UUID], status: str
    ) -> int:
        """Bulk update alert status."""
        stmt = (
            update(Alert)
            .where(and_(Alert.tenant_id == tenant_id, Alert.id.in_(alert_ids)))
            .values(analysis_status=status, updated_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def delete(self, alert_id: UUID, tenant_id: str) -> bool:
        """Hard delete alert from database.

        Note: This intentionally does NOT delete from alert_human_ids table
        to ensure human_readable_ids are never reused after deletion.
        """
        stmt = select(Alert).where(
            and_(Alert.id == alert_id, Alert.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        alert = result.scalar_one_or_none()

        if alert:
            await self.session.delete(alert)
            await self.session.flush()
            # Note: We do NOT delete from alert_human_ids to prevent ID reuse
            return True
        return False

    async def get_by_entity(
        self,
        tenant_id: str,
        entity_value: str,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[Alert]:
        """Search alerts by entity value in OCSF actor/device JSONB fields.

        The entity_type parameter is accepted for API compatibility but ignored
        since OCSF encodes entity type implicitly (actor vs device).
        """
        from sqlalchemy import String, cast

        conditions = [
            Alert.tenant_id == tenant_id,
            or_(
                cast(Alert.actor, String).ilike(f"%{entity_value}%"),
                cast(Alert.device, String).ilike(f"%{entity_value}%"),
            ),
        ]

        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(desc(Alert.triggering_event_time))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ioc(
        self,
        tenant_id: str,
        ioc_value: str,
        ioc_type: str | None = None,
        limit: int = 20,
    ) -> list[Alert]:
        """Search alerts by IOC value in OCSF observables JSONB field.

        The ioc_type parameter is accepted for API compatibility but ignored
        since OCSF stores IOC type within the observables array items.
        """
        from sqlalchemy import String, cast

        conditions = [
            Alert.tenant_id == tenant_id,
            cast(Alert.observables, String).ilike(f"%{ioc_value}%"),
        ]

        stmt = (
            select(Alert)
            .where(and_(*conditions))
            .order_by(desc(Alert.triggering_event_time))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_text(
        self, tenant_id: str, query: str, limit: int = 20
    ) -> list[Alert]:
        """Full-text search across alert fields."""
        from sqlalchemy import String, cast

        # Simple implementation - search in title, rule_name, source columns,
        # and OCSF JSONB fields (observables, actor).
        # In production, you'd want to use PostgreSQL full-text search or similar.
        search_pattern = f"%{query}%"

        stmt = (
            select(Alert)
            .where(
                and_(
                    Alert.tenant_id == tenant_id,
                    or_(
                        Alert.title.ilike(search_pattern),
                        Alert.rule_name.ilike(search_pattern),
                        Alert.source_vendor.ilike(search_pattern),
                        Alert.source_product.ilike(search_pattern),
                        cast(Alert.observables, String).ilike(search_pattern),
                        cast(Alert.actor, String).ilike(search_pattern),
                    ),
                )
            )
            .order_by(desc(Alert.triggering_event_time))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_paused_at_workflow_builder(
        self, tenant_id: str | None = None
    ) -> list[Alert]:
        """
        Find alerts paused during workflow generation.

        Used by reconciliation job to identify alerts waiting for
        workflow generation to complete.

        Note: The status 'paused_workflow_building' is the authoritative signal.
        The current_step may be 'workflow_execution' because the pipeline
        advances it before checking if we need to pause.

        Args:
            tenant_id: If provided, restrict results to this tenant only.

        Returns:
            List of alerts with:
            - AlertAnalysis.status = 'paused_workflow_building'
        """
        conditions = [AlertAnalysis.status == AnalysisStatus.PAUSED_WORKFLOW_BUILDING]
        if tenant_id is not None:
            conditions.append(Alert.tenant_id == tenant_id)
        stmt = (
            select(Alert)
            .join(AlertAnalysis, Alert.id == AlertAnalysis.alert_id)
            .where(and_(*conditions))
            .order_by(Alert.created_at)  # FIFO order
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def try_resume_alert(self, tenant_id: str, alert_id: str) -> bool:
        """
        Try to resume alert (first-come-first-serve coordination).

        Atomically transitions AlertAnalysis from paused to running.
        Multiple workers can call this simultaneously - only one succeeds.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID

        Returns:
            bool: True if this worker successfully claimed the alert, False if
                  another worker already resumed it
        """
        # Use UPDATE with WHERE to ensure atomic claim on AlertAnalysis
        stmt = (
            update(AlertAnalysis)
            .where(
                and_(
                    AlertAnalysis.alert_id == alert_id,
                    AlertAnalysis.tenant_id == tenant_id,
                    AlertAnalysis.status
                    == AnalysisStatus.PAUSED_WORKFLOW_BUILDING,  # Only if still paused
                )
            )
            .values(status=AnalysisStatus.RUNNING, updated_at=datetime.now(UTC))
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        # rowcount > 0 means we successfully claimed it
        return result.rowcount > 0

    async def find_paused_alerts_by_rule_name(
        self, tenant_id: str, rule_name: str
    ) -> list[Alert]:
        """
        Find paused alerts for a specific rule_name (analysis group title).

        Used by push-based resume when workflow generation completes.
        After creating the routing rule, the job calls this to find all alerts
        waiting for this specific workflow.

        Args:
            tenant_id: Tenant identifier
            rule_name: Rule name (analysis group title) to match

        Returns:
            List of alerts with:
            - Alert.rule_name = rule_name
            - AlertAnalysis.status = 'paused_workflow_building'
        """
        stmt = (
            select(Alert)
            .join(AlertAnalysis, Alert.id == AlertAnalysis.alert_id)
            .where(
                and_(
                    Alert.tenant_id == tenant_id,
                    Alert.rule_name == rule_name,
                    AlertAnalysis.status == AnalysisStatus.PAUSED_WORKFLOW_BUILDING,
                )
            )
            .order_by(Alert.created_at)  # FIFO order
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_stuck_running_alerts(
        self, stuck_threshold_minutes: int = 60, tenant_id: str | None = None
    ) -> list[tuple[Alert, AlertAnalysis]]:
        """
        Find alerts stuck in 'running' status for too long.

        Stuck job detector. Called by reconciliation to find alerts
        where the worker may have crashed during processing.

        Args:
            stuck_threshold_minutes: Minutes after which alert is considered stuck
                                     (default: 60 minutes)
            tenant_id: If provided, restrict results to this tenant only.

        Returns:
            List of (Alert, AlertAnalysis) tuples for stuck alerts
        """
        threshold = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)
        conditions = [
            AlertAnalysis.status == AnalysisStatus.RUNNING,
            AlertAnalysis.updated_at < threshold,
        ]
        if tenant_id is not None:
            conditions.append(Alert.tenant_id == tenant_id)
        stmt = (
            select(Alert, AlertAnalysis)
            .join(AlertAnalysis, Alert.id == AlertAnalysis.alert_id)
            .where(and_(*conditions))
            .order_by(AlertAnalysis.updated_at)  # Oldest first
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def mark_stuck_alert_failed(
        self, tenant_id: str, alert_id: str, analysis_id: str, error: str
    ) -> bool:
        """
        Mark a stuck alert's analysis as failed.

        Stuck job detector. Called by reconciliation when an alert
        has been stuck in 'running' status beyond the threshold.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID
            analysis_id: AlertAnalysis UUID
            error: Error message explaining why it was marked failed

        Returns:
            bool: True if successfully marked failed, False otherwise
        """
        now = datetime.now(UTC)

        # Update AlertAnalysis to failed
        stmt = (
            update(AlertAnalysis)
            .where(
                and_(
                    AlertAnalysis.id == analysis_id,
                    AlertAnalysis.tenant_id == tenant_id,
                    AlertAnalysis.status
                    == AnalysisStatus.RUNNING,  # Only if still running
                )
            )
            .values(
                status=AnalysisStatus.FAILED,
                error_message=error,
                completed_at=now,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)

        if result.rowcount > 0:
            # Also update the Alert's analysis_status
            alert_stmt = (
                update(Alert)
                .where(
                    and_(
                        Alert.id == alert_id,
                        Alert.tenant_id == tenant_id,
                    )
                )
                .values(analysis_status=AlertStatus.FAILED, updated_at=now)
            )
            await self.session.execute(alert_stmt)
            await self.session.commit()
            return True

        return False

    async def find_mismatched_alert_statuses(
        self, tenant_id: str | None = None
    ) -> list[tuple[Alert, AlertAnalysis]]:
        """
        Find alerts where Alert.analysis_status doesn't match AlertAnalysis.status.

        Specifically finds cases where:
        - Alert.analysis_status = 'in_progress'
        - AlertAnalysis.status IN ('failed', 'completed')

        This happens when update_alert_analysis_status() fails (e.g., API 500 error
        due to partition lock exhaustion) after AlertAnalysis.status was updated.

        Args:
            tenant_id: If provided, restrict results to this tenant only.

        Returns:
            List of (Alert, AlertAnalysis) tuples for mismatched alerts
        """
        conditions = [
            Alert.analysis_status == AlertStatus.IN_PROGRESS,
            AlertAnalysis.status.in_([AnalysisStatus.FAILED, AnalysisStatus.COMPLETED]),
        ]
        if tenant_id is not None:
            conditions.append(Alert.tenant_id == tenant_id)
        # Join on current_analysis_id — only check the CURRENT analysis,
        # not old ones.  Without this, a re-analysis (in_progress) with
        # old failed analyses would be falsely synced back to "failed".
        stmt = (
            select(Alert, AlertAnalysis)
            .join(AlertAnalysis, Alert.current_analysis_id == AlertAnalysis.id)
            .where(and_(*conditions))
            .order_by(AlertAnalysis.updated_at)  # Oldest first
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def sync_alert_status_from_analysis(
        self, tenant_id: str, alert_id: str, new_status: str
    ) -> bool:
        """
        Sync Alert.analysis_status from AlertAnalysis.status.

        Called by reconciliation when there's a mismatch between the two statuses.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert UUID
            new_status: New status to set on Alert.analysis_status

        Returns:
            bool: True if successfully synced, False otherwise
        """
        now = datetime.now(UTC)

        stmt = (
            update(Alert)
            .where(
                and_(
                    Alert.id == alert_id,
                    Alert.tenant_id == tenant_id,
                    Alert.analysis_status == AlertStatus.IN_PROGRESS,
                )
            )
            .values(analysis_status=new_status, updated_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        return result.rowcount > 0


class AlertAnalysisRepository:
    """Repository for alert analysis operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_analysis(self, alert_id: UUID, tenant_id: str) -> AlertAnalysis:
        """Create new analysis for an alert."""
        analysis = AlertAnalysis(
            alert_id=alert_id,
            tenant_id=tenant_id,
            status=AnalysisStatus.RUNNING,
            steps_progress={},
        )
        self.session.add(analysis)
        await self.session.flush()
        return analysis

    async def update_step_progress(
        self,
        analysis_id: UUID,
        step: str,
        completed: bool,
        error: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Update progress for a specific analysis step."""
        conditions = [AlertAnalysis.id == analysis_id]
        if tenant_id is not None:
            conditions.append(AlertAnalysis.tenant_id == tenant_id)
        stmt = select(AlertAnalysis).where(and_(*conditions))
        result = await self.session.execute(stmt)
        analysis = result.scalar_one_or_none()

        if analysis:
            analysis.update_step_progress(step, completed, error)
            # Mark JSONB field as modified so SQLAlchemy detects the change
            flag_modified(analysis, "steps_progress")
            await self.session.flush()

    async def get_by_id(
        self, analysis_id: UUID, tenant_id: str
    ) -> AlertAnalysis | None:
        """Get analysis by ID."""
        stmt = select(AlertAnalysis).where(
            and_(
                AlertAnalysis.id == analysis_id,
                AlertAnalysis.tenant_id == tenant_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_current_analysis(
        self, alert_id: UUID, tenant_id: str
    ) -> AlertAnalysis | None:
        """Get the most recent analysis for an alert."""
        stmt = (
            select(AlertAnalysis)
            .where(
                and_(
                    AlertAnalysis.alert_id == alert_id,
                    AlertAnalysis.tenant_id == tenant_id,
                )
            )
            .order_by(desc(AlertAnalysis.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_analysis_history(
        self, alert_id: UUID, tenant_id: str
    ) -> list[AlertAnalysis]:
        """Get all analyses for an alert."""
        stmt = (
            select(AlertAnalysis)
            .where(
                and_(
                    AlertAnalysis.alert_id == alert_id,
                    AlertAnalysis.tenant_id == tenant_id,
                )
            )
            .order_by(desc(AlertAnalysis.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_completed(
        self,
        analysis_id: UUID,
        disposition_id: UUID,
        confidence: int,
        short_summary: str,
        long_summary: str,
        tenant_id: str | None = None,
    ) -> None:
        """Mark analysis as completed with results."""
        conditions = [AlertAnalysis.id == analysis_id]
        if tenant_id is not None:
            conditions.append(AlertAnalysis.tenant_id == tenant_id)
        stmt = select(AlertAnalysis).where(and_(*conditions))
        result = await self.session.execute(stmt)
        analysis = result.scalar_one_or_none()

        if analysis:
            analysis.mark_completed()
            analysis.disposition_id = disposition_id
            analysis.confidence = confidence
            analysis.short_summary = short_summary
            analysis.long_summary = long_summary
            await self.session.flush()

    async def increment_workflow_gen_retry_count(
        self, analysis_id: UUID, tenant_id: str | None = None
    ) -> int:
        """
        Increment workflow generation retry count and update last failure timestamp.

        Called by reconciliation when resuming an alert after a failed
        workflow generation. Returns the new retry count.

        Args:
            analysis_id: AlertAnalysis UUID
            tenant_id: If provided, restrict to this tenant only.

        Returns:
            int: New retry count after increment
        """
        now = datetime.now(UTC)
        conditions = [AlertAnalysis.id == analysis_id]
        if tenant_id is not None:
            conditions.append(AlertAnalysis.tenant_id == tenant_id)
        stmt = select(AlertAnalysis).where(and_(*conditions))
        result = await self.session.execute(stmt)
        analysis = result.scalar_one_or_none()

        if analysis:
            current_count = analysis.workflow_gen_retry_count or 0
            analysis.workflow_gen_retry_count = current_count + 1
            analysis.workflow_gen_last_failure_at = now
            analysis.updated_at = now
            await self.session.flush()
            return analysis.workflow_gen_retry_count

        return 0

    async def find_orphaned_running_analyses(
        self, threshold_minutes: int = 2, tenant_id: str | None = None
    ) -> list[AlertAnalysis]:
        """Find analyses stuck in 'running' with no step progress.

        Issue #5: Detects analyses where the ARQ job was silently lost
        (Redis flaky) or the worker crashed before starting any step.
        These have status='running' but empty/null steps_progress.

        Args:
            threshold_minutes: Minimum age in minutes to consider orphaned (default: 2)
            tenant_id: If provided, restrict results to this tenant only.

        Returns:
            List of orphaned AlertAnalysis records
        """
        threshold = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        conditions = [
            AlertAnalysis.status == AnalysisStatus.RUNNING,
            AlertAnalysis.created_at < threshold,
            or_(
                AlertAnalysis.steps_progress.is_(None),
                AlertAnalysis.steps_progress == {},
            ),
        ]
        if tenant_id is not None:
            conditions.append(AlertAnalysis.tenant_id == tenant_id)
        stmt = (
            select(AlertAnalysis)
            .where(and_(*conditions))
            .order_by(AlertAnalysis.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_running(self, analysis_id: UUID, tenant_id: str) -> bool:
        """
        Transition analysis back to running status (e.g., after HITL resume).

        HITL — Project Kalymnos: When a human answers a HITL question, the
        analysis must leave paused_human_review and return to running so the
        pipeline can continue executing.

        Args:
            analysis_id: AlertAnalysis UUID
            tenant_id: Tenant identifier (required to prevent cross-tenant updates)

        Returns:
            bool: True if analysis was updated, False if not found
        """
        now = datetime.now(UTC)
        stmt = (
            update(AlertAnalysis)
            .where(AlertAnalysis.id == analysis_id)
            .where(AlertAnalysis.tenant_id == tenant_id)
            .where(AlertAnalysis.status == AnalysisStatus.PAUSED_HUMAN_REVIEW)
            .values(
                status=AnalysisStatus.RUNNING,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def mark_failed(
        self, analysis_id: UUID, error_message: str, tenant_id: str
    ) -> bool:
        """
        Mark analysis as failed with error message.

        Used when max retries exceeded or stuck alert detected.

        Args:
            analysis_id: AlertAnalysis UUID
            error_message: Reason for failure
            tenant_id: Tenant identifier (required to prevent cross-tenant updates)

        Returns:
            bool: True if analysis was updated, False if not found
        """
        now = datetime.now(UTC)
        stmt = (
            update(AlertAnalysis)
            .where(AlertAnalysis.id == analysis_id)
            .where(AlertAnalysis.tenant_id == tenant_id)
            .values(
                status=AnalysisStatus.FAILED,
                error_message=error_message,
                completed_at=now,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def get_by_alert_id(
        self, alert_id: UUID, tenant_id: str
    ) -> AlertAnalysis | None:
        """
        Get the current (most recent) analysis for an alert.

        Used by reconciliation to check retry count and backoff.

        Args:
            alert_id: Alert UUID
            tenant_id: Tenant identifier

        Returns:
            AlertAnalysis or None if not found
        """
        stmt = (
            select(AlertAnalysis)
            .where(
                and_(
                    AlertAnalysis.alert_id == alert_id,
                    AlertAnalysis.tenant_id == tenant_id,
                )
            )
            .order_by(desc(AlertAnalysis.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_paused_for_human_review(self) -> list[AlertAnalysis]:
        """
        Find analyses paused for human review (HITL — Project Kalymnos).

        Used by reconciliation to detect expired HITL pauses and fail them.

        Returns:
            List of AlertAnalysis records with status = 'paused_human_review'
        """
        stmt = (
            select(AlertAnalysis)
            .where(AlertAnalysis.status == AnalysisStatus.PAUSED_HUMAN_REVIEW)
            .order_by(AlertAnalysis.updated_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DispositionRepository:
    """Repository for disposition operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_system_dispositions(self) -> list[Disposition]:
        """Get all system-defined dispositions."""
        stmt = (
            select(Disposition)
            .where(Disposition.is_system.is_(True))
            .order_by(Disposition.priority_score)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_category(
        self, category: str | None = None
    ) -> dict[str, list[Disposition]]:
        """Get dispositions grouped by category."""
        conditions = []
        if category:
            conditions.append(Disposition.category == category)

        stmt = (
            select(Disposition)
            .where(and_(*conditions) if conditions else True)
            .order_by(Disposition.category, Disposition.priority_score)
        )
        result = await self.session.execute(stmt)
        dispositions = result.scalars().all()

        # Group by category
        grouped = {}
        for disp in dispositions:
            if disp.category not in grouped:
                grouped[disp.category] = []
            grouped[disp.category].append(disp)

        return grouped

    async def find_by_priority_range(
        self, min_priority: int, max_priority: int
    ) -> list[Disposition]:
        """Find dispositions within priority range."""
        stmt = (
            select(Disposition)
            .where(
                and_(
                    Disposition.priority_score >= min_priority,
                    Disposition.priority_score <= max_priority,
                )
            )
            .order_by(Disposition.priority_score)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_custom_disposition(
        self, category: str, subcategory: str, **kwargs
    ) -> Disposition:
        """Create custom user-defined disposition."""
        disposition = Disposition(
            category=category, subcategory=subcategory, is_system=False, **kwargs
        )
        self.session.add(disposition)
        await self.session.flush()
        return disposition
