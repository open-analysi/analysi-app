"""Knowledge Dependency Graph endpoints."""

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
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.schemas.kdg import (
    EdgeCreate,
    EdgeDirection,
    EdgeResponse,
    EdgeUpdate,
    GlobalGraphResponse,
    GraphResponse,
    NodeResponse,
    NodeType,
)
from analysi.services.kdg import KDGService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/kdg",
    tags=["kdg"],
    dependencies=[Depends(require_permission("knowledge_units", "read"))],
)


async def get_kdg_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KDGService:
    """Dependency injection for KDGService."""
    return KDGService(session)


@router.post(
    "/edges",
    response_model=ApiResponse[EdgeResponse],
    status_code=201,
    dependencies=[Depends(require_permission("knowledge_units", "update"))],
)
async def create_edge(
    request: Request,
    edge_data: EdgeCreate,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
) -> ApiResponse[EdgeResponse]:
    """Create a new edge between nodes."""
    try:
        edge = await service.create_edge(edge_data, tenant)
        return api_response(edge, request=request)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            logger.warning("edge_node_not_found", error=msg)
            raise HTTPException(status_code=400, detail="Referenced node not found")
        raise HTTPException(status_code=400, detail="Invalid edge definition")


@router.get("/edges/{edge_id}", response_model=ApiResponse[EdgeResponse])
async def get_edge(
    request: Request,
    edge_id: UUID,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
) -> ApiResponse[EdgeResponse]:
    """Get edge details including source and target nodes."""
    edge = await service.get_edge(edge_id, tenant)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    return api_response(edge, request=request)


@router.put(
    "/edges/{edge_id}",
    response_model=ApiResponse[EdgeResponse],
    dependencies=[Depends(require_permission("knowledge_units", "update"))],
)
async def update_edge(
    request: Request,
    edge_id: UUID,
    edge_update: EdgeUpdate,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
) -> ApiResponse[EdgeResponse]:
    """Update an edge's metadata and properties."""
    try:
        updated_edge = await service.update_edge(edge_id, edge_update, tenant)
        if not updated_edge:
            raise HTTPException(status_code=404, detail="Edge not found")
        return api_response(updated_edge, request=request)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid edge update")


@router.delete(
    "/edges/{edge_id}",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge_units", "update"))],
)
async def delete_edge(
    edge_id: UUID,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
) -> None:
    """Delete an edge."""
    deleted = await service.delete_edge(edge_id, tenant)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")


@router.get("/nodes/{node_id}", response_model=ApiResponse[NodeResponse])
async def get_node(
    request: Request,
    node_id: UUID,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
) -> ApiResponse[NodeResponse]:
    """Get node details (Task or KU)."""
    node = await service.get_node(node_id, tenant)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return api_response(node, request=request)


@router.get("/nodes", response_model=ApiListResponse[NodeResponse])
async def list_nodes(
    request: Request,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
    pagination: PaginationParams = Depends(),
    type: NodeType | None = Query(None, description="Filter by node type"),
    q: str | None = Query(None, description="Search query for name/description"),
) -> ApiListResponse[NodeResponse]:
    """List and search nodes."""
    nodes, total = await service.list_nodes(
        tenant_id=tenant,
        node_type=type,
        search_query=q,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return api_list_response(nodes, total=total, request=request, pagination=pagination)


@router.get("/nodes/{node_id}/edges", response_model=ApiListResponse[EdgeResponse])
async def get_node_edges(
    request: Request,
    node_id: UUID,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
    pagination: PaginationParams = Depends(),
    direction: EdgeDirection = Query(
        EdgeDirection.BOTH,
        description="Edge direction: in (incoming), out (outgoing), both",
    ),
) -> ApiListResponse[EdgeResponse]:
    """Get edges connected to a node."""
    edges, total = await service.get_node_edges(
        node_id=node_id,
        tenant_id=tenant,
        direction=direction,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return api_list_response(edges, total=total, request=request, pagination=pagination)


@router.get("/nodes/{node_id}/graph", response_model=ApiResponse[GraphResponse])
async def get_node_graph(
    request: Request,
    node_id: UUID,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
    depth: int = Query(2, ge=1, le=5, description="Traversal depth (1-5)"),
) -> ApiResponse[GraphResponse]:
    """Get subgraph starting from node using BFS traversal."""
    graph = await service.get_node_graph(node_id, tenant, depth)
    return api_response(graph, request=request)


@router.get("/graph", response_model=ApiResponse[GlobalGraphResponse])
async def get_global_graph(
    request: Request,
    tenant: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KDGService, Depends(get_kdg_service)],
    include_tasks: bool = Query(True, description="Include task nodes"),
    include_knowledge_units: bool = Query(True, description="Include KU nodes"),
    include_tools: bool = Query(True, description="Include tool nodes"),
    include_skills: bool = Query(True, description="Include skill nodes"),
    depth: int | None = Query(None, ge=1, le=5, description="Traversal depth limit"),
    max_nodes: int | None = Query(
        None, ge=1, le=1000, description="Maximum nodes to return"
    ),
) -> ApiResponse[GlobalGraphResponse]:
    """Get global knowledge graph with filtering options."""
    graph_data = await service.get_global_graph(
        tenant_id=tenant,
        include_tasks=include_tasks,
        include_knowledge_units=include_knowledge_units,
        include_tools=include_tools,
        include_skills=include_skills,
        depth=depth,
        max_nodes=max_nodes,
    )
    return api_response(GlobalGraphResponse(**graph_data), request=request)
