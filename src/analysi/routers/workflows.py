"""
FastAPI routers for workflow endpoints.
Handles workflow and node template CRUD operations.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    PaginationParams,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.auth.messages import INTERNAL_ERROR
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.audit import get_audit_context
from analysi.dependencies.tenant import get_tenant_id
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.workflow import (
    AddEdgeRequest,
    AddNodeRequest,
    ComposeRequest,
    ComposeResponse,
    NodeTemplateCreate,
    NodeTemplateResponse,
    TemplateCodeValidation,
    ValidationResult,
    WorkflowCreate,
    WorkflowDefinitionValidation,
    WorkflowEdgeMutationResponse,
    WorkflowNodeMutationResponse,
    WorkflowNodeUpdate,
    WorkflowResponse,
    WorkflowTypesClearedResponse,
    WorkflowUpdate,
)
from analysi.schemas.workflow_validation import (
    WorkflowTypeApplyResponse,
    WorkflowTypeValidationRequest,
    WorkflowTypeValidationResponse,
)
from analysi.services.workflow import NodeTemplateService, WorkflowService
from analysi.services.workflow_composer import WorkflowComposerService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/workflows",
    tags=["workflows"],
    dependencies=[Depends(require_permission("workflows", "read"))],
)


async def get_workflow_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowService:
    """Dependency injection for WorkflowService."""
    return WorkflowService(session)


async def get_template_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NodeTemplateService:
    """Dependency injection for NodeTemplateService."""
    return NodeTemplateService(session)


async def get_composer_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowComposerService:
    """Dependency injection for WorkflowComposerService."""
    return WorkflowComposerService(session)


# Workflow Endpoints
@router.post(
    "",
    response_model=ApiResponse[WorkflowResponse],
    status_code=201,
    dependencies=[Depends(require_permission("workflows", "create"))],
)
async def create_workflow(
    request: Request,
    workflow_data: WorkflowCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    validate: bool = Query(
        False, description="Enable schema validation during creation"
    ),
) -> ApiResponse[WorkflowResponse]:
    """
    Create a complete workflow with nodes and edges.

    Accepts a single JSON document containing the complete workflow definition
    and creates all related entities atomically.

    Use ?validate=true to enable schema validation before creation.
    """
    try:
        result = await service.create_workflow(
            tenant_id, workflow_data, audit_context, validate=validate
        )
        return api_response(result, request=request)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow definition")
    except Exception:
        logger.exception("create_workflow_failed")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.get("", response_model=ApiListResponse[WorkflowResponse])
async def list_workflows(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    pagination: PaginationParams = Depends(),
    name: str | None = Query(None, description="Filter by workflow name"),
    app: str | None = Query(None, description="Filter by content pack name"),
) -> ApiListResponse[WorkflowResponse]:
    """List workflows with pagination and filtering."""
    workflows, result_meta = await service.list_workflows(
        tenant_id=tenant_id,
        skip=pagination.offset,
        limit=pagination.limit,
        name_filter=name,
        app=app,
    )

    from analysi.models.workflow import enrich_workflow_json

    workflow_responses = [
        WorkflowResponse(**enrich_workflow_json(w)) for w in workflows
    ]

    return api_list_response(
        workflow_responses,
        total=result_meta["total"],
        request=request,
        pagination=pagination,
    )


# Node Template Endpoints
@router.post(
    "/node-templates",
    response_model=ApiResponse[NodeTemplateResponse],
    status_code=201,
    # Admin-only: templates contain Python code that runs via exec().
    # Only the 3 system templates (identity, merge, collect) exist by default.
    dependencies=[Depends(require_permission("workflows", "delete"))],
)
async def create_node_template(
    request: Request,
    template_data: NodeTemplateCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[NodeTemplateService, Depends(get_template_service)],
) -> ApiResponse[NodeTemplateResponse]:
    """Create a new node template. Admin-only — templates execute Python code."""
    try:
        template = await service.create_template(template_data, tenant_id)
        return api_response(template, request=request)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template definition")
    except Exception:
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.get("/node-templates", response_model=ApiListResponse[NodeTemplateResponse])
async def list_node_templates(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[NodeTemplateService, Depends(get_template_service)],
    pagination: PaginationParams = Depends(),
    name: str | None = Query(None, description="Filter by template name"),
    enabled_only: bool = Query(False, description="Only return enabled templates"),
) -> ApiListResponse[NodeTemplateResponse]:
    """List node templates with pagination and filtering."""
    templates, result_meta = await service.list_templates(
        tenant_id=tenant_id,
        skip=pagination.offset,
        limit=pagination.limit,
        enabled_only=enabled_only,
        name_filter=name,
    )

    return api_list_response(
        templates,
        total=result_meta["total"],
        request=request,
        pagination=pagination,
    )


@router.get(
    "/node-templates/{template_id}", response_model=ApiResponse[NodeTemplateResponse]
)
async def get_node_template(
    request: Request,
    template_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[NodeTemplateService, Depends(get_template_service)],
) -> ApiResponse[NodeTemplateResponse]:
    """Get node template by ID."""
    template = await service.get_template(template_id, tenant_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return api_response(template, request=request)


@router.delete(
    "/node-templates/{template_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "delete"))],
)
async def delete_node_template(
    template_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[NodeTemplateService, Depends(get_template_service)],
) -> None:
    """Delete node template."""
    deleted = await service.delete_template(template_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")


@router.post("/validate", response_model=ApiResponse[WorkflowDefinitionValidation])
async def validate_workflow_definition(
    request: Request,
    workflow_data: WorkflowCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowDefinitionValidation]:
    """
    Validate workflow definition without creating it.

    Useful for development and testing workflow definitions.
    """
    try:
        validation_result = await service.validate_workflow_definition(
            workflow_data, tenant_id
        )
        return api_response(
            WorkflowDefinitionValidation(**validation_result), request=request
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow definition")


# Workflow Composer Endpoint
@router.post(
    "/compose",
    response_model=ApiResponse[ComposeResponse],
    status_code=200,
    dependencies=[Depends(require_permission("workflows", "create"))],
)
async def compose_workflow(
    request: Request,
    compose_request: ComposeRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowComposerService, Depends(get_composer_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[ComposeResponse]:
    """
    Compose workflow from simple array format.

    Accepts an array of cy_names, shortcuts, or nested arrays and intelligently
    composes a type-safe workflow. Returns errors, warnings, and questions for
    user decisions.
    """
    try:
        # Always derive created_by from authenticated user (prevent impersonation)
        created_by = audit_context.actor_user_id

        result = await service.compose_workflow(
            composition=compose_request.composition,
            workflow_name=compose_request.name,
            workflow_description=compose_request.description or "",
            tenant_id=tenant_id,
            created_by=created_by,
            execute=compose_request.execute,
            audit_context=audit_context,
        )

        # Convert internal models to response schemas
        from analysi.schemas.workflow import (
            CompositionError as ComposeErrorSchema,
        )
        from analysi.schemas.workflow import (
            CompositionPlan as ComposePlanSchema,
        )
        from analysi.schemas.workflow import (
            CompositionQuestion as ComposeQuestionSchema,
        )
        from analysi.schemas.workflow import (
            CompositionWarning as ComposeWarningSchema,
        )

        compose_response = ComposeResponse(
            status=result.status,
            workflow_id=result.workflow_id,
            errors=[
                ComposeErrorSchema(
                    error_type=e.error_type, message=e.message, context=e.context
                )
                for e in result.errors
            ],
            warnings=[
                ComposeWarningSchema(
                    warning_type=w.warning_type, message=w.message, context=w.context
                )
                for w in result.warnings
            ],
            questions=[
                ComposeQuestionSchema(
                    question_id=q.question_id,
                    question_type=q.question_type,
                    message=q.message,
                    options=q.options,
                    suggested=q.suggested,
                    context=q.context,
                )
                for q in result.questions
            ],
            plan=(
                ComposePlanSchema(
                    nodes=result.plan.nodes,
                    edges=result.plan.edges,
                    inferred_input_schema=result.plan.inferred_input_schema,
                    inferred_output_schema=result.plan.inferred_output_schema,
                    node_details=result.plan.node_details,
                )
                if result.plan
                else None
            ),
        )
        return api_response(compose_response, request=request)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid composition request")
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="Workflow composition not yet implemented",
        )


@router.post(
    "/node-templates/validate", response_model=ApiResponse[TemplateCodeValidation]
)
async def validate_template_code(
    request: Request,
    template_data: NodeTemplateCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[NodeTemplateService, Depends(get_template_service)],
) -> ApiResponse[TemplateCodeValidation]:
    """
    Validate template code without creating the template.

    Useful for development and testing template code.
    """
    try:
        validation_result = await service.validate_template_code(
            template_data.code, template_data.language
        )
        return api_response(
            TemplateCodeValidation(**validation_result), request=request
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template code")


# Workflow ID-based endpoints (moved to end to avoid path conflicts)
@router.get("/{workflow_id}", response_model=ApiResponse[WorkflowResponse])
async def get_workflow(
    request: Request,
    workflow_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowResponse]:
    """
    Get workflow by ID with enriched data.

    Returns complete workflow JSON with joined template code and task details.
    """
    workflow = await service.get_workflow(tenant_id, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return api_response(workflow, request=request)


@router.delete(
    "/{workflow_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "delete"))],
)
async def delete_workflow(
    workflow_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> None:
    """Delete workflow and all related nodes/edges."""
    deleted = await service.delete_workflow(tenant_id, workflow_id, audit_context)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")


# Type Validation API Endpoints
@router.post(
    "/{workflow_id}/validate-types",
    response_model=ApiResponse[WorkflowTypeValidationResponse],
)
async def validate_workflow_types(
    request: Request,
    workflow_id: UUID,
    type_request: WorkflowTypeValidationRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowTypeValidationResponse]:
    """
    Validate workflow type safety using type propagation.

    Returns type validation results without persisting to database.
    Use this endpoint to check if a workflow is type-safe before applying changes.
    """
    try:
        result = await service.validate_workflow_types(
            tenant_id, workflow_id, type_request.initial_input_schema
        )
        return api_response(WorkflowTypeValidationResponse(**result), request=request)
    except ValueError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail="Workflow not found")
        raise HTTPException(status_code=400, detail="Invalid type validation request")
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="Type validation not yet implemented",
        )


@router.post(
    "/{workflow_id}/apply-types",
    response_model=ApiResponse[WorkflowTypeApplyResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def apply_workflow_types(
    request: Request,
    workflow_id: UUID,
    type_request: WorkflowTypeValidationRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowTypeApplyResponse]:
    """
    Validate workflow types AND persist type annotations to database.

    First validates the workflow, then if valid (or valid with warnings),
    persists the inferred type annotations to WorkflowNode.schemas.
    """
    try:
        result = await service.apply_workflow_types(
            tenant_id, workflow_id, type_request.initial_input_schema
        )
        return api_response(WorkflowTypeApplyResponse(**result), request=request)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid type application request")
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="Type application not yet implemented",
        )


@router.delete(
    "/{workflow_id}/types",
    response_model=ApiResponse[WorkflowTypesClearedResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def clear_workflow_types(
    request: Request,
    workflow_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowTypesClearedResponse]:
    """
    Clear type annotations from workflow.

    Removes inferred_input, inferred_output, type_checked, and validated_at
    fields from all workflow nodes.
    """
    try:
        result = await service.clear_workflow_types(tenant_id, workflow_id)
        return api_response(WorkflowTypesClearedResponse(**result), request=request)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request")


# ========== Mutation Endpoints ==========


@router.put(
    "/{workflow_id}",
    response_model=ApiResponse[WorkflowResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def replace_workflow(
    request: Request,
    workflow_id: UUID,
    workflow_data: WorkflowCreate,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowResponse]:
    """
    Replace an existing workflow with new data (full update).

    This endpoint replaces all nodes and edges while preserving the workflow ID.
    Use PATCH for metadata-only updates.
    """
    from analysi.models.workflow import enrich_workflow_json
    from analysi.repositories.workflow import NotFoundError

    try:
        workflow = await service.replace_workflow(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            workflow_data=workflow_data,
            audit_context=audit_context,
        )
        enriched = enrich_workflow_json(workflow)
        return api_response(WorkflowResponse(**enriched), request=request)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow definition")


@router.patch(
    "/{workflow_id}",
    response_model=ApiResponse[WorkflowResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def update_workflow(
    request: Request,
    workflow_id: UUID,
    update_data: WorkflowUpdate,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowResponse]:
    """Update workflow metadata (name, description, io_schema, data_samples)."""
    from analysi.models.workflow import enrich_workflow_json
    from analysi.repositories.workflow import NotFoundError

    try:
        workflow = await service.update_workflow_metadata(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            update_data=update_data,
            audit_context=audit_context,
        )
        enriched = enrich_workflow_json(workflow)
        return api_response(WorkflowResponse(**enriched), request=request)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post(
    "/{workflow_id}/nodes",
    response_model=ApiResponse[WorkflowNodeMutationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def add_workflow_node(
    request: Request,
    workflow_id: UUID,
    node_request: AddNodeRequest,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowNodeMutationResponse]:
    """Add a node to an existing workflow."""
    from sqlalchemy.exc import IntegrityError

    from analysi.repositories.workflow import NotFoundError

    try:
        node = await service.add_node(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            node_request=node_request,
            audit_context=audit_context,
        )
        # Handle kind as string or enum
        kind_value = node.kind.value if hasattr(node.kind, "value") else node.kind
        return api_response(
            WorkflowNodeMutationResponse(
                id=str(node.id),
                node_id=node.node_id,
                kind=kind_value,
                name=node.name,
                is_start_node=node.is_start_node,
                schemas=node.schemas,
            ),
            request=request,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workflow node request")
    except IntegrityError as e:
        # Check specific constraint type
        error_str = str(e.orig) if e.orig else str(e)
        logger.error("workflow_node_integrity_error", error=error_str)
        if "node_id" in error_str or "uq_workflow_nodes" in error_str:
            raise HTTPException(
                status_code=409, detail="Node with this node_id already exists"
            )
        if "task_id" in error_str or "fk_" in error_str.lower():
            raise HTTPException(
                status_code=400, detail="Invalid reference in workflow node"
            )
        raise HTTPException(
            status_code=409, detail="Database integrity constraint violated"
        )


@router.patch(
    "/{workflow_id}/nodes/{node_id}",
    response_model=ApiResponse[WorkflowNodeMutationResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def update_workflow_node(
    request: Request,
    workflow_id: UUID,
    node_id: str,
    update_data: WorkflowNodeUpdate,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowNodeMutationResponse]:
    """Update a workflow node's properties."""
    from analysi.repositories.workflow import NotFoundError

    try:
        node = await service.update_node(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            node_id=node_id,
            update_data=update_data,
            audit_context=audit_context,
        )
        # Handle kind as string or enum
        kind_value = node.kind.value if hasattr(node.kind, "value") else node.kind
        return api_response(
            WorkflowNodeMutationResponse(
                id=str(node.id),
                node_id=node.node_id,
                kind=kind_value,
                name=node.name,
                is_start_node=node.is_start_node,
                schemas=node.schemas,
            ),
            request=request,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Node not found")


@router.delete(
    "/{workflow_id}/nodes/{node_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def delete_workflow_node(
    workflow_id: UUID,
    node_id: str,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> None:
    """Delete a node from workflow. Connected edges are cascade deleted."""
    from analysi.repositories.workflow import NotFoundError

    try:
        deleted = await service.remove_node(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            node_id=node_id,
            audit_context=audit_context,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Node not found")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post(
    "/{workflow_id}/edges",
    response_model=ApiResponse[WorkflowEdgeMutationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def add_workflow_edge(
    request: Request,
    workflow_id: UUID,
    edge_request: AddEdgeRequest,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[WorkflowEdgeMutationResponse]:
    """Add an edge between two nodes in a workflow."""
    from sqlalchemy.exc import IntegrityError

    from analysi.repositories.workflow import NotFoundError

    try:
        edge = await service.add_edge(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            edge_request=edge_request,
            audit_context=audit_context,
        )
        # Use request data for node IDs (avoid lazy loading)
        return api_response(
            WorkflowEdgeMutationResponse(
                id=str(edge.id),
                edge_id=edge.edge_id,
                from_node_id=edge_request.from_node_id,
                to_node_id=edge_request.to_node_id,
                alias=edge.alias,
            ),
            request=request,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Edge with this edge_id already exists"
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid edge definition")


@router.delete(
    "/{workflow_id}/edges/{edge_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def delete_workflow_edge(
    workflow_id: UUID,
    edge_id: str,
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> None:
    """Delete an edge from workflow."""
    from analysi.repositories.workflow import NotFoundError

    try:
        deleted = await service.remove_edge(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            edge_id=edge_id,
            audit_context=audit_context,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Edge not found")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post(
    "/{workflow_id}/validate",
    response_model=ApiResponse[ValidationResult],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def validate_workflow_on_demand(
    request: Request,
    workflow_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApiResponse[ValidationResult]:
    """
    On-demand validation: DAG structure + type propagation.

    Updates workflow status to 'validated' or 'invalid'.
    """
    from analysi.repositories.workflow import NotFoundError

    try:
        result = await service.validate_workflow_on_demand(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
        )
        return api_response(result, request=request)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Workflow not found")
