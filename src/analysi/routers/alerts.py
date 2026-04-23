"""Alert management REST API endpoints."""

import json
import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    PaginationParams,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.auth.webhook_signature import verify_signature
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)
from analysi.schemas.alert import (
    AlertAnalysisResponse,
    AlertCreate,
    AlertResponse,
    AlertStatus,
    AlertUpdate,
    AnalysisCancelledResponse,
    AnalysisCompletedResponse,
    AnalysisProgress,
    AnalysisStartedResponse,
    AnalysisStatus,
    AnalysisStatusUpdatedResponse,
    AnalysisStepUpdatedResponse,
    DispositionResponse,
)
from analysi.services.alert_service import (
    AlertAnalysisService,
    AlertService,
    DispositionService,
)

logger = get_logger(__name__)
router = APIRouter(
    prefix="/{tenant}",
    tags=["alerts"],
    dependencies=[Depends(require_permission("alerts", "read"))],
)


# ────────────────────────────────────────────────────────────────────────
# Webhook signature verification
# ────────────────────────────────────────────────────────────────────────
# Per-tenant signing secrets are configured via a single JSON-encoded env
# var so any character allowed in a tenant ID (`-`, `.`, `@`, `_`) round-
# trips safely without env-var-name escaping issues:
#
#   ANALYSI_ALERT_WEBHOOK_SECRETS={"default":"abc","acme-prod":"xyz"}
#
# Inject via Kubernetes Secret + ExternalSecret/Sealed-Secret. Setting any
# tenant key requires that tenant's ingestion calls include a valid
# X-Webhook-Signature header. Tenants NOT in the map continue to accept
# unsigned alerts — this keeps the feature opt-in per tenant.


_WEBHOOK_SECRETS_ENV = "ANALYSI_ALERT_WEBHOOK_SECRETS"


def _parse_webhook_secrets_map(raw: str | None) -> dict[str, str]:
    """Parse the JSON object env var into a {tenant: secret} dict.

    Defensive: malformed JSON, non-object root, or non-string values are
    silently dropped (logged as warnings would be noisier than helpful at
    every request). Returns an empty dict so the feature stays disabled
    when misconfigured rather than failing closed and breaking ingestion.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        k: v for k, v in parsed.items() if isinstance(k, str) and isinstance(v, str)
    }


def get_tenant_webhook_secret(
    tenant: str = Depends(get_tenant_id),
) -> str | None:
    """Look up the tenant's alert-webhook signing secret, if configured."""
    secrets = _parse_webhook_secrets_map(os.environ.get(_WEBHOOK_SECRETS_ENV))
    return secrets.get(tenant) or None


async def verify_alert_webhook_signature(
    request: Request,
    current_user: CurrentUser = Depends(require_current_user),
    secret: str | None = Depends(get_tenant_webhook_secret),
    x_webhook_signature: str | None = Header(default=None),
) -> None:
    """Verify the incoming alert payload's HMAC signature when configured.

    - If no secret is configured for the tenant, this is a no-op.
    - Internal system-actor callers (integrations-worker posting alerts via
      the system API key) are exempt: they've already authenticated via a
      trusted internal credential and the HMAC is meant for untrusted
      external sources.
    - Otherwise the X-Webhook-Signature header must be present and match
      HMAC-SHA256(body, secret); missing or wrong signature → 401.
    """
    if secret is None:
        return  # opt-in; not enabled for this tenant

    # Internal callers (system API key) are not externally-delivered webhooks.
    # Requiring them to sign payloads would break integrations-worker ingestion
    # for no added security benefit (the system key is already trusted).
    if current_user.actor_type == "system":
        return

    if not x_webhook_signature:
        logger.warning(
            "alert_webhook_signature_missing",
            tenant=request.path_params.get("tenant"),
        )
        raise HTTPException(
            status_code=401, detail="Missing X-Webhook-Signature header"
        )

    body = await request.body()
    if not verify_signature(body, x_webhook_signature, secret):
        logger.warning(
            "alert_webhook_signature_invalid",
            tenant=request.path_params.get("tenant"),
        )
        raise HTTPException(status_code=401, detail="Invalid X-Webhook-Signature")


# Alert CRUD Endpoints
@router.post(
    "/alerts",
    response_model=ApiResponse[AlertResponse],
    status_code=201,
    dependencies=[
        Depends(require_permission("alerts", "create")),
        # Optional HMAC verification; no-op when the tenant has no signing
        # secret configured (preserves existing inbound flows).
        Depends(verify_alert_webhook_signature),
    ],
)
async def create_alert(
    alert_data: AlertCreate,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AlertResponse]:
    """Create new alert with deduplication."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)

    # Log the incoming alert data for debugging
    logger.info(
        "Creating alert",
        tenant_id=tenant,
        title=alert_data.title,
        severity=alert_data.severity,
        source_product=alert_data.source_product,
        triggering_event_time=str(alert_data.triggering_event_time),
    )

    try:
        result = await service.create_alert(tenant, alert_data)
        logger.info(
            "Alert created successfully",
            tenant_id=tenant,
            alert_id=str(result.alert_id),
            human_readable_id=result.human_readable_id,
        )
        return api_response(result, request=request)
    except ValueError as e:
        error_msg = str(e)
        if "Duplicate alert detected" in error_msg:
            # Extract raw_data_hash from error message if available
            import re

            hash_match = re.search(r"raw_data_hash: ([a-f0-9]+)", error_msg)
            raw_data_hash = hash_match.group(1) if hash_match else "unknown"

            logger.warning(
                "Duplicate alert detected",
                tenant_id=tenant,
                title=alert_data.title,
                raw_data_hash=raw_data_hash,
                triggering_event_time=str(alert_data.triggering_event_time),
            )

            raise HTTPException(
                status_code=409,
                detail=f"Duplicate alert detected. Raw data hash: {raw_data_hash}. "
                + "Duplicate detection based on: SHA-256 of raw_data",
            )
        raise


@router.get("/alerts", response_model=ApiListResponse[AlertResponse])
async def list_alerts(
    request: Request,
    tenant: str = Depends(get_tenant_id),
    severity: list[str] | None = Query(None),
    status: str | None = None,
    source_vendor: str | None = None,
    source_product: str | None = None,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    disposition_category: str | None = Query(
        None, description="Filter by disposition category"
    ),
    disposition_subcategory: str | None = Query(
        None, description="Filter by disposition subcategory"
    ),
    min_confidence: int | None = Query(
        None, ge=0, le=100, description="Filter by minimum confidence percentage"
    ),
    max_confidence: int | None = Query(
        None, ge=0, le=100, description="Filter by maximum confidence percentage"
    ),
    include_short_summary: bool = Query(
        False, description="Include analysis short summary"
    ),
    sort_by: str = Query(
        "triggering_event_time",
        description="Sort by field: human_readable_id, title, severity, analysis_status, current_disposition_display_name, triggering_event_time, created_at, updated_at",
    ),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AlertResponse]:
    """List alerts with filtering and pagination."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)

    filters = {
        "severity": severity,
        "status": status,
        "source_vendor": source_vendor,
        "source_product": source_product,
        "time_from": time_from,
        "time_to": time_to,
        "disposition_category": disposition_category,
        "disposition_subcategory": disposition_subcategory,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
    }

    result = await service.list_alerts(
        tenant, filters, limit, offset, include_short_summary, sort_by, sort_order
    )
    pagination = PaginationParams(limit=limit, offset=offset)
    return api_list_response(
        result.alerts, total=result.total, request=request, pagination=pagination
    )


# Search & Discovery Endpoints (must come before parametric routes)
@router.get("/alerts/search", response_model=ApiListResponse[AlertResponse])
async def search_alerts(
    q: str,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AlertResponse]:
    """Search alerts with text search."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)
    result = await service.search_alerts(tenant, q, limit)
    return api_list_response(result, total=len(result), request=request)


@router.get(
    "/alerts/by-entity/{entity_value}", response_model=ApiListResponse[AlertResponse]
)
async def get_alerts_by_entity(
    entity_value: str,
    request: Request,
    entity_type: str | None = None,
    tenant: str = Depends(get_tenant_id),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AlertResponse]:
    """Get alerts by entity value."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)
    result = await service.get_alerts_by_entity(
        tenant, entity_value, entity_type, limit
    )
    return api_list_response(result, total=len(result), request=request)


@router.get("/alerts/by-ioc/{ioc_value}", response_model=ApiListResponse[AlertResponse])
async def get_alerts_by_ioc(
    ioc_value: str,
    request: Request,
    ioc_type: str | None = None,
    tenant: str = Depends(get_tenant_id),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AlertResponse]:
    """Get alerts by IOC value."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)
    result = await service.get_alerts_by_ioc(tenant, ioc_value, ioc_type, limit)
    return api_list_response(result, total=len(result), request=request)


@router.get("/alerts/{alert_id}", response_model=ApiResponse[AlertResponse])
async def get_alert(
    alert_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    include_analysis: bool = True,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AlertResponse]:
    """Get alert with optional analysis expansion."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)
    alert = await service.get_alert(tenant, alert_id, include_analysis)

    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return api_response(alert, request=request)


@router.patch(
    "/alerts/{alert_id}",
    response_model=ApiResponse[AlertResponse],
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def update_alert(
    alert_id: UUID,
    update_data: AlertUpdate,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AlertResponse]:
    """Update alert (only mutable fields allowed)."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)

    try:
        result = await service.update_alert(tenant, alert_id, update_data)
        return api_response(result, request=request)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alert not found")


@router.delete(
    "/alerts/{alert_id}",
    status_code=204,
    dependencies=[Depends(require_permission("alerts", "delete"))],
)
async def delete_alert(
    alert_id: UUID,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard delete an alert."""
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)
    disposition_repo = DispositionRepository(db)

    service = AlertService(alert_repo, analysis_repo, disposition_repo, db)
    deleted = await service.delete_alert(tenant, alert_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


# Disposition Management Endpoints
@router.get("/dispositions", response_model=ApiListResponse[DispositionResponse])
async def list_dispositions(
    request: Request,
    tenant: str = Depends(get_tenant_id),
    category: str | None = None,
    requires_escalation: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[DispositionResponse]:
    """List all dispositions with optional filtering."""
    disposition_repo = DispositionRepository(db)
    service = DispositionService(disposition_repo, db)

    result = await service.list_dispositions(category, requires_escalation)
    return api_list_response(result, total=len(result), request=request)


@router.get(
    "/dispositions/by-category",
    response_model=ApiResponse[dict[str, list[DispositionResponse]]],
)
async def get_dispositions_by_category(
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, list[DispositionResponse]]]:
    """Get dispositions grouped by category."""
    disposition_repo = DispositionRepository(db)
    service = DispositionService(disposition_repo, db)

    result = await service.get_by_category()
    return api_response(result, request=request)


@router.get(
    "/dispositions/{disposition_id}", response_model=ApiResponse[DispositionResponse]
)
async def get_disposition(
    disposition_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[DispositionResponse]:
    """Get specific disposition by ID."""
    disposition_repo = DispositionRepository(db)
    service = DispositionService(disposition_repo, db)

    disposition = await service.get_disposition(disposition_id)
    if not disposition:
        raise HTTPException(
            status_code=404, detail=f"Disposition {disposition_id} not found"
        )

    return api_response(disposition, request=request)


# ============================================================================
# Alert Analysis Endpoints
# These endpoints initiate and track alert analysis via ARQ workers
# ============================================================================


@router.post(
    "/alerts/{alert_id}/analyze",
    response_model=ApiResponse[AnalysisStartedResponse],
    status_code=202,
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def start_alert_analysis(
    alert_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_current_user),
) -> ApiResponse[AnalysisStartedResponse]:
    """
    Start analysis for an alert.

    This endpoint:
    1. Creates new alert_analysis record using existing service
    2. Queues ARQ job for processing
    3. Returns 202 Accepted with analysis_id
    """
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)

    analysis_service = AlertAnalysisService(analysis_repo, alert_repo, db)

    try:
        # Create analysis
        analysis = await analysis_service.start_analysis(tenant, alert_id)

        # Queue ARQ job for worker processing
        try:
            from analysi.alert_analysis.worker import queue_alert_analysis

            # Pass actor for audit attribution (db_user_id when available)
            actor_id = str(current_user.db_user_id) if current_user.db_user_id else None
            await queue_alert_analysis(
                tenant, str(alert_id), str(analysis.id), actor_user_id=actor_id
            )
        except ImportError:
            # If arq is not installed (API container), skip queuing
            # This allows testing without the full worker setup
            logger.warning(
                "ARQ not available - analysis will not be processed by worker"
            )
        except Exception as queue_error:
            # Issue #5: Queue failure (e.g., Redis down) must not leave
            # analysis in "running" state. db.commit() below is NOT reached,
            # so the session rolls back and the analysis record is discarded.
            logger.error("failed_to_queue_analysis_job", error=str(queue_error))
            raise HTTPException(
                status_code=503,
                detail="Failed to queue analysis job. Please retry.",
            )

        await db.commit()

        return api_response(
            AnalysisStartedResponse(
                analysis_id=str(analysis.id),
                status="accepted",
                message="Analysis started successfully",
            ),
            request=request,
        )

    except HTTPException:
        raise  # Let HTTPExceptions (e.g., 503 from queue failure) propagate
    except Exception as e:
        logger.error(
            "failed_to_start_analysis_for_alert", alert_id=alert_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to start alert analysis")


@router.get(
    "/alerts/{alert_id}/analysis/progress",
    response_model=ApiResponse[AnalysisProgress | dict],
)
async def get_analysis_progress(
    alert_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalysisProgress | dict]:
    """
    Get current analysis progress for an alert.

    Returns current step and completion status, or an empty object when
    the alert has no analysis yet.
    """
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)

    analysis_service = AlertAnalysisService(analysis_repo, alert_repo, db)

    try:
        progress = await analysis_service.get_analysis_progress(tenant, alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alert not found")

    if not progress:
        return api_response({}, request=request)
    return api_response(AnalysisProgress(**progress), request=request)


@router.get(
    "/alerts/{alert_id}/analyses", response_model=ApiListResponse[AlertAnalysisResponse]
)
async def get_alert_analyses(
    alert_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AlertAnalysisResponse]:
    """
    Get all analysis history for an alert.

    Returns list of all analysis runs (supports re-analysis).
    """
    alert_repo = AlertRepository(db)
    analysis_repo = AlertAnalysisRepository(db)

    analysis_service = AlertAnalysisService(analysis_repo, alert_repo, db)

    try:
        analyses = await analysis_service.get_analysis_history(tenant, alert_id)
        return api_list_response(analyses, total=len(analyses), request=request)

    except ValueError:
        raise HTTPException(status_code=404, detail="Alert not found")


@router.put(
    "/analyses/{analysis_id}/step",
    response_model=ApiResponse[AnalysisStepUpdatedResponse],
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def update_analysis_step(
    analysis_id: UUID,
    request: Request,
    step_name: str,
    completed: bool,
    error: str | None = None,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalysisStepUpdatedResponse]:
    """
    Update analysis step progress.

    This endpoint is used by the worker to update step progress.
    """
    from sqlalchemy import select

    from analysi.models.alert import AlertAnalysis

    # Get the analysis to verify it exists and belongs to tenant
    stmt = select(AlertAnalysis).where(
        AlertAnalysis.id == analysis_id, AlertAnalysis.tenant_id == tenant
    )
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Update step progress
    analysis.update_step_progress(step_name, completed, error)

    # Flag the JSONB field as modified so SQLAlchemy knows to update it
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(analysis, "steps_progress")

    # If completing a step, clear current_step
    if completed and analysis.current_step == step_name:
        analysis.current_step = None
    # If starting a step (not completed), set as current
    elif not completed:
        analysis.current_step = step_name

    await db.commit()

    return api_response(
        AnalysisStepUpdatedResponse(status="updated", step=step_name), request=request
    )


class CompleteAnalysisBody(BaseModel):
    """Body for the complete_analysis endpoint."""

    disposition_id: UUID | None = None
    confidence: int = 0
    short_summary: str = ""
    long_summary: str = ""
    workflow_id: UUID | None = None
    workflow_run_id: UUID | None = None
    disposition_category: str | None = None
    disposition_subcategory: str | None = None
    disposition_display_name: str | None = None
    disposition_confidence: int | None = None


@router.put(
    "/analyses/{analysis_id}/complete",
    response_model=ApiResponse[AnalysisCompletedResponse],
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def complete_analysis(
    analysis_id: UUID,
    request: Request,
    body: CompleteAnalysisBody,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalysisCompletedResponse]:
    """
    Complete an analysis with disposition results.

    This endpoint is used by the worker to mark analysis as completed.
    Accepts a JSON body with optional disposition fields.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select, update

    from analysi.models.alert import Alert, AlertAnalysis

    # Get the analysis
    stmt = select(AlertAnalysis).where(
        AlertAnalysis.id == analysis_id, AlertAnalysis.tenant_id == tenant
    )
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Mark the final step as completed if there's a current step
    if analysis.current_step and analysis.steps_progress:
        analysis.update_step_progress(analysis.current_step, completed=True)
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(analysis, "steps_progress")

    # Transition guard: only emit control event on first completion
    emit_disposition_ready = analysis.status != "completed"

    # Update analysis with results
    analysis.disposition_id = body.disposition_id
    analysis.confidence = body.confidence
    analysis.short_summary = body.short_summary
    analysis.long_summary = body.long_summary
    analysis.status = AnalysisStatus.COMPLETED
    analysis.completed_at = datetime.now(UTC)
    analysis.current_step = None

    if body.workflow_id:
        analysis.workflow_id = body.workflow_id
    if body.workflow_run_id:
        analysis.workflow_run_id = body.workflow_run_id

    # Update the associated alert's denormalized fields
    if (
        body.disposition_category
        or body.disposition_subcategory
        or body.disposition_display_name
        or body.disposition_confidence is not None
    ):
        alert_stmt = (
            update(Alert)
            .where(Alert.current_analysis_id == analysis_id, Alert.tenant_id == tenant)
            .values(
                analysis_status=AlertStatus.COMPLETED,
                current_disposition_category=body.disposition_category,
                current_disposition_subcategory=body.disposition_subcategory,
                current_disposition_display_name=body.disposition_display_name,
                current_disposition_confidence=body.disposition_confidence,
                updated_at=datetime.now(UTC),
            )
        )
        await db.execute(alert_stmt)
    else:
        # At minimum, update the analysis status
        alert_stmt = (
            update(Alert)
            .where(Alert.current_analysis_id == analysis_id, Alert.tenant_id == tenant)
            .values(analysis_status="completed", updated_at=datetime.now(UTC))
        )
        await db.execute(alert_stmt)

    # Emit disposition:ready control event (same transaction, idempotent via transition guard)
    if emit_disposition_ready:
        from analysi.repositories.control_event_repository import (
            ControlEventRepository,
        )

        event_repo = ControlEventRepository(db)
        await event_repo.insert(
            tenant_id=tenant,
            channel="disposition:ready",
            payload={
                "alert_id": str(analysis.alert_id),
                "analysis_id": str(analysis_id),
                "disposition_id": (
                    str(body.disposition_id) if body.disposition_id else None
                ),
                "disposition_display_name": body.disposition_display_name,
                "confidence": body.confidence,
            },
        )

    await db.commit()

    return api_response(
        AnalysisCompletedResponse(status="completed", analysis_id=str(analysis_id)),
        request=request,
    )


@router.put(
    "/analyses/{analysis_id}/status",
    response_model=ApiResponse[AnalysisStatusUpdatedResponse],
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def update_analysis_status(
    analysis_id: UUID,
    request: Request,
    status: str,
    error: str | None = None,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalysisStatusUpdatedResponse]:
    """
    Update analysis status.

    This endpoint is used by the worker to update analysis status (running, failed, etc).
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from analysi.models.alert import AlertAnalysis

    # Validate status - must match DB constraint chk_analysis_status
    valid_statuses = {
        "running",
        "paused",
        "paused_human_review",
        "completed",
        "failed",
        "cancelled",
    }
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    # Get the analysis
    stmt = select(AlertAnalysis).where(
        AlertAnalysis.id == analysis_id, AlertAnalysis.tenant_id == tenant
    )
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Terminal-state guard: cancelled is a terminal state set by the user.
    # Reject any worker attempt to overwrite it (running, failed, completed, etc.)
    # so that an in-flight job cannot un-cancel a cancelled analysis.
    if analysis.status == "cancelled":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update status: analysis is cancelled (terminal state). "
            f"Attempted transition: cancelled → {status}",
        )

    # Transition guard: only emit control event on first failure
    emit_analysis_failed = (
        status == AnalysisStatus.FAILED and analysis.status != AnalysisStatus.FAILED
    )

    # Update status and timestamps
    analysis.status = status
    analysis.updated_at = datetime.now(UTC)

    if status == AnalysisStatus.RUNNING:
        analysis.started_at = datetime.now(UTC)
    elif status == AnalysisStatus.COMPLETED:
        analysis.completed_at = datetime.now(UTC)
    elif status == AnalysisStatus.FAILED and error:
        analysis.error_message = error

    # Emit analysis:failed control event (same transaction, idempotent via transition guard)
    if emit_analysis_failed:
        from analysi.repositories.control_event_repository import (
            ControlEventRepository,
        )

        event_repo = ControlEventRepository(db)
        await event_repo.insert(
            tenant_id=tenant,
            channel="analysis:failed",
            payload={
                "alert_id": str(analysis.alert_id),
                "analysis_id": str(analysis_id),
                "error": error or "",
            },
        )

    await db.commit()

    return api_response(
        AnalysisStatusUpdatedResponse(status="updated", analysis_status=status),
        request=request,
    )


@router.put(
    "/alerts/{alert_id}/analysis-status",
    response_model=ApiResponse[AnalysisStatusUpdatedResponse],
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def update_alert_analysis_status(
    alert_id: UUID,
    request: Request,
    analysis_status: str,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalysisStatusUpdatedResponse]:
    """
    Update alert's analysis_status field.

    This endpoint is used by the worker to sync alert status with analysis status.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from analysi.models.alert import Alert

    # Validate status - must match DB constraint chk_alerts_analysis_status
    valid_statuses = {"new", "in_progress", "completed", "failed", "cancelled"}
    if analysis_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    # Get the alert
    stmt = select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Terminal-state guard: cancelled is a terminal state set by the user.
    # Reject worker attempts to overwrite it.
    if alert.analysis_status == "cancelled":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update status: alert analysis is cancelled (terminal state). "
            f"Attempted transition: cancelled → {analysis_status}",
        )

    # Update status
    alert.analysis_status = analysis_status
    alert.updated_at = datetime.now(UTC)

    await db.commit()

    return api_response(
        AnalysisStatusUpdatedResponse(
            status="updated", analysis_status=analysis_status
        ),
        request=request,
    )


@router.post(
    "/alerts/{alert_id}/analysis/cancel",
    response_model=ApiResponse[AnalysisCancelledResponse],
    dependencies=[Depends(require_permission("alerts", "update"))],
)
async def cancel_alert_analysis(
    alert_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AnalysisCancelledResponse]:
    """
    Cancel an in-progress or paused alert analysis.

    Only allowed when the current analysis status is 'running' or
    'paused_workflow_building'. Terminal states (completed, failed, cancelled)
    return 409.

    The in-flight worker job will detect the 409 from update_analysis_status
    and abort without overwriting the cancelled status.

    Returns:
        {"status": "cancelled", "previous_status": "<prior status>"}
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from analysi.models.alert import Alert, AlertAnalysis

    # Cancellable states — all others are terminal or not started
    cancellable = {"running", "paused", "paused_human_review"}

    # Load the alert (scoped to tenant)
    stmt = select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Must have an active analysis
    if not alert.current_analysis_id:
        raise HTTPException(
            status_code=404, detail="No active analysis found for this alert"
        )

    # Load the analysis
    stmt2 = select(AlertAnalysis).where(
        AlertAnalysis.id == alert.current_analysis_id,
        AlertAnalysis.tenant_id == tenant,
    )
    result2 = await db.execute(stmt2)
    analysis = result2.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Active analysis record not found")

    if analysis.status not in cancellable:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel analysis in '{analysis.status}' state. "
            f"Only {sorted(cancellable)} are cancellable.",
        )

    previous_status = analysis.status
    now = datetime.now(UTC)

    # Atomically mark both the analysis and the alert as cancelled
    analysis.status = AnalysisStatus.CANCELLED
    analysis.updated_at = now

    alert.analysis_status = AlertStatus.CANCELLED
    alert.updated_at = now

    await db.commit()

    logger.info(
        "alert_analysis_cancelled",
        alert_id=str(alert_id),
        previous_status=previous_status,
        tenant_id=tenant,
    )

    return api_response(
        AnalysisCancelledResponse(status="cancelled", previous_status=previous_status),
        request=request,
    )
