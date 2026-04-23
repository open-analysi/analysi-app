"""Knowledge Unit management endpoints."""

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
from analysi.dependencies.audit import get_audit_context
from analysi.dependencies.tenant import get_tenant_id
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.knowledge_index import (
    AddEntriesRequest,
    AddEntriesResponse,
    EntryResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from analysi.schemas.knowledge_unit import (
    DocumentKUCreate,
    DocumentKUResponse,
    DocumentKUUpdate,
    IndexKUCreate,
    IndexKUResponse,
    IndexKUUpdate,
    KUResponse,
    TableKUCreate,
    TableKUResponse,
    TableKUUpdate,
)
from analysi.services.knowledge_index import (
    CollectionNotFoundError,
    EmbeddingModelMismatchError,
    KnowledgeIndexService,
    NoEmbeddingProviderError,
)
from analysi.services.knowledge_unit import KnowledgeUnitService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/knowledge-units",
    tags=["knowledge-units"],
    dependencies=[Depends(require_permission("knowledge_units", "read"))],
)


async def get_ku_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeUnitService:
    """Dependency injection for KnowledgeUnitService."""
    return KnowledgeUnitService(session)


# --- Helper functions ---


def _build_table_response(table) -> dict:
    """Build response dict from Table KU + Component."""
    return {
        "id": table.component.id,
        "tenant_id": table.component.tenant_id,
        "ku_type": "table",
        "name": table.component.name,
        "description": table.component.description,
        "version": table.component.version,
        "status": table.component.status,
        "visible": table.component.visible,
        "system_only": table.component.system_only,
        "app": table.component.app,
        "categories": table.component.categories,
        "created_by": table.component.created_by,
        "cy_name": table.component.cy_name,
        "namespace": table.component.namespace,
        "table_schema": table.schema or {},
        "content": table.content or {},
        "row_count": table.row_count,
        "column_count": table.column_count,
        "file_path": table.file_path,
        "created_at": table.created_at,
        "updated_at": table.updated_at,
        "last_used_at": table.component.last_used_at,
    }


def _build_document_response(doc) -> dict:
    """Build response dict from Document KU + Component."""
    return {
        "id": doc.component.id,
        "tenant_id": doc.component.tenant_id,
        "ku_type": "document",
        "name": doc.component.name,
        "description": doc.component.description,
        "version": doc.component.version,
        "status": doc.component.status,
        "visible": doc.component.visible,
        "system_only": doc.component.system_only,
        "app": doc.component.app,
        "categories": doc.component.categories,
        "created_by": doc.component.created_by,
        "cy_name": doc.component.cy_name,
        "namespace": doc.component.namespace,
        "content": doc.content,
        "markdown_content": doc.markdown_content,
        "doc_format": doc.doc_format,
        "document_type": doc.document_type,
        "source_url": doc.source_url,
        "file_path": doc.file_path,
        "metadata": doc.doc_metadata or {},
        "word_count": doc.word_count,
        "character_count": doc.character_count,
        "page_count": doc.page_count,
        "language": doc.language,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "last_used_at": doc.component.last_used_at,
    }


def _build_index_response(index) -> dict:
    """Build response dict from Index KU + Component."""
    return {
        "id": index.component.id,
        "tenant_id": index.component.tenant_id,
        "ku_type": "index",
        "name": index.component.name,
        "description": index.component.description,
        "version": index.component.version,
        "status": index.component.status,
        "visible": index.component.visible,
        "system_only": index.component.system_only,
        "app": index.component.app,
        "categories": index.component.categories,
        "created_by": index.component.created_by,
        "cy_name": index.component.cy_name,
        "namespace": index.component.namespace,
        "index_type": index.index_type,
        "vector_database": index.vector_database,
        "embedding_model": index.embedding_model,
        "embedding_dimensions": index.embedding_dimensions,
        "backend_type": index.backend_type or "pgvector",
        "chunking_config": index.chunking_config or {},
        "build_status": index.build_status,
        "build_started_at": index.build_started_at,
        "build_completed_at": index.build_completed_at,
        "build_error_message": index.build_error_message,
        "index_stats": index.index_stats or {},
        "last_sync_at": index.last_sync_at,
        "created_at": index.created_at,
        "updated_at": index.updated_at,
        "last_used_at": index.component.last_used_at,
    }


# --- Table KU Endpoints ---


@router.post(
    "/tables",
    response_model=ApiResponse[TableKUResponse],
    status_code=201,
    dependencies=[Depends(require_permission("knowledge_units", "create"))],
)
async def create_table_ku(
    request: Request,
    table_data: TableKUCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[TableKUResponse]:
    """Create a new Table Knowledge Unit."""
    table = await service.create_table(
        tenant_id, table_data, created_by=audit_context.actor_user_id
    )
    return api_response(
        TableKUResponse.model_validate(_build_table_response(table)), request=request
    )


@router.get("/tables/{id}", response_model=ApiResponse[TableKUResponse])
async def get_table_ku(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> ApiResponse[TableKUResponse]:
    """Get a Table KU by ID."""
    table = await service.get_table(id, tenant_id)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return api_response(
        TableKUResponse.model_validate(_build_table_response(table)), request=request
    )


@router.put(
    "/tables/{id}",
    response_model=ApiResponse[TableKUResponse],
    dependencies=[Depends(require_permission("knowledge_units", "update"))],
)
async def update_table_ku(
    request: Request,
    id: UUID,
    update_data: TableKUUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> ApiResponse[TableKUResponse]:
    """Update an existing Table KU."""
    table = await service.update_table(id, tenant_id, update_data)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return api_response(
        TableKUResponse.model_validate(_build_table_response(table)), request=request
    )


@router.delete(
    "/tables/{id}",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge_units", "delete"))],
)
async def delete_table_ku(
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> None:
    """Delete a Table KU."""
    success = await service.delete_ku(id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Table not found")


@router.get("/tables", response_model=ApiListResponse[TableKUResponse])
async def list_table_kus(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    pagination: PaginationParams = Depends(),
    app: str | None = Query(None, description="Filter by content pack name"),
) -> ApiListResponse[TableKUResponse]:
    """List Table KUs with pagination."""
    tables, result_meta = await service.list_tables(
        tenant_id=tenant_id,
        app=app,
        skip=pagination.offset,
        limit=pagination.limit,
    )
    total = result_meta["total"]

    table_responses = [
        TableKUResponse.model_validate(_build_table_response(table)) for table in tables
    ]
    return api_list_response(
        table_responses, total=total, request=request, pagination=pagination
    )


# --- Document KU Endpoints ---


@router.post(
    "/documents",
    response_model=ApiResponse[DocumentKUResponse],
    status_code=201,
    dependencies=[Depends(require_permission("knowledge_units", "create"))],
)
async def create_document_ku(
    request: Request,
    doc_data: DocumentKUCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[DocumentKUResponse]:
    """Create a new Document Knowledge Unit."""
    doc = await service.create_document(
        tenant_id, doc_data, created_by=audit_context.actor_user_id
    )
    return api_response(
        DocumentKUResponse.model_validate(_build_document_response(doc)),
        request=request,
    )


@router.get("/documents/{id}", response_model=ApiResponse[DocumentKUResponse])
async def get_document_ku(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> ApiResponse[DocumentKUResponse]:
    """Get a Document KU by ID."""
    doc = await service.get_document(id, tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return api_response(
        DocumentKUResponse.model_validate(_build_document_response(doc)),
        request=request,
    )


@router.put(
    "/documents/{id}",
    response_model=ApiResponse[DocumentKUResponse],
    dependencies=[Depends(require_permission("knowledge_units", "update"))],
)
async def update_document_ku(
    request: Request,
    id: UUID,
    update_data: DocumentKUUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> ApiResponse[DocumentKUResponse]:
    """Update an existing Document KU."""
    doc = await service.update_document(id, tenant_id, update_data)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return api_response(
        DocumentKUResponse.model_validate(_build_document_response(doc)),
        request=request,
    )


@router.delete(
    "/documents/{id}",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge_units", "delete"))],
)
async def delete_document_ku(
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> None:
    """Delete a Document KU."""
    success = await service.delete_ku(id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")


@router.get("/documents", response_model=ApiListResponse[DocumentKUResponse])
async def list_document_kus(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    pagination: PaginationParams = Depends(),
    app: str | None = Query(None, description="Filter by content pack name"),
) -> ApiListResponse[DocumentKUResponse]:
    """List Document KUs with pagination."""
    documents, result_meta = await service.list_documents(
        tenant_id=tenant_id,
        skip=pagination.offset,
        limit=pagination.limit,
        app=app,
    )
    total = result_meta["total"]

    doc_responses = [
        DocumentKUResponse.model_validate(_build_document_response(doc))
        for doc in documents
    ]
    return api_list_response(
        doc_responses, total=total, request=request, pagination=pagination
    )


# --- Index KU Endpoints ---


@router.post(
    "/indexes",
    response_model=ApiResponse[IndexKUResponse],
    status_code=201,
    dependencies=[Depends(require_permission("knowledge_units", "create"))],
)
async def create_index_ku(
    request: Request,
    index_data: IndexKUCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[IndexKUResponse]:
    """Create a new Index Knowledge Unit (management only, no build)."""
    index = await service.create_index(
        tenant_id, index_data, created_by=audit_context.actor_user_id
    )
    return api_response(
        IndexKUResponse.model_validate(_build_index_response(index)), request=request
    )


@router.get("/indexes/{id}", response_model=ApiResponse[IndexKUResponse])
async def get_index_ku(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> ApiResponse[IndexKUResponse]:
    """Get an Index KU by ID."""
    index = await service.get_index(id, tenant_id)
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    return api_response(
        IndexKUResponse.model_validate(_build_index_response(index)), request=request
    )


@router.put(
    "/indexes/{id}",
    response_model=ApiResponse[IndexKUResponse],
    dependencies=[Depends(require_permission("knowledge_units", "update"))],
)
async def update_index_ku(
    request: Request,
    id: UUID,
    update_data: IndexKUUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> ApiResponse[IndexKUResponse]:
    """Update an existing Index KU."""
    index = await service.update_index(id, tenant_id, update_data)
    if not index:
        raise HTTPException(status_code=404, detail="Index not found")
    return api_response(
        IndexKUResponse.model_validate(_build_index_response(index)), request=request
    )


@router.delete(
    "/indexes/{id}",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge_units", "delete"))],
)
async def delete_index_ku(
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
) -> None:
    """Delete an Index KU."""
    success = await service.delete_ku(id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Index not found")


@router.get("/indexes", response_model=ApiListResponse[IndexKUResponse])
async def list_index_kus(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    pagination: PaginationParams = Depends(),
    app: str | None = Query(None, description="Filter by content pack name"),
) -> ApiListResponse[IndexKUResponse]:
    """List Index KUs with pagination."""
    indexes, result_meta = await service.list_indexes(
        tenant_id=tenant_id,
        skip=pagination.offset,
        limit=pagination.limit,
        app=app,
    )
    total = result_meta["total"]

    index_responses = [
        IndexKUResponse.model_validate(_build_index_response(index))
        for index in indexes
    ]
    return api_list_response(
        index_responses, total=total, request=request, pagination=pagination
    )


# --- Cross-Type Search Endpoint ---


@router.get("", response_model=ApiListResponse[KUResponse])
async def search_knowledge_units(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeUnitService, Depends(get_ku_service)],
    pagination: PaginationParams = Depends(),
    q: str | None = Query(
        None, min_length=1, description="Search query for name and description"
    ),
    ku_type: str | None = Query(
        None, description="Filter by KU type (table/document/index)"
    ),
    status: str | None = Query(None, description="Filter by status (enabled/disabled)"),
    categories: list[str] | None = Query(
        None, description="Filter by categories (AND semantics)"
    ),
) -> ApiListResponse[KUResponse]:
    """Search across all Knowledge Unit types."""
    # Validate status parameter
    if status and status not in ["enabled", "disabled"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid status value. Must be 'enabled' or 'disabled'",
        )

    if q:
        kus, result_meta = await service.search_kus(
            tenant_id=tenant_id,
            query=q,
            ku_type=ku_type,
            status=status,
            skip=pagination.offset,
            limit=pagination.limit,
            categories=categories,
        )
    else:
        kus, result_meta = await service.list_all_kus(
            tenant_id=tenant_id,
            ku_type=ku_type,
            status=status,
            skip=pagination.offset,
            limit=pagination.limit,
            categories=categories,
        )

    total = result_meta["total"]

    ku_responses = []
    for ku in kus:
        response_data = {
            "id": ku.component.id,
            "tenant_id": ku.component.tenant_id,
            "ku_type": ku.ku_type,
            "name": ku.component.name,
            "description": ku.component.description,
            "version": ku.component.version,
            "status": ku.component.status,
            "visible": ku.component.visible,
            "system_only": ku.component.system_only,
            "app": ku.component.app,
            "categories": ku.component.categories,
            "created_by": ku.component.created_by,
            "cy_name": ku.component.cy_name,
            "namespace": ku.component.namespace,
            "created_at": ku.created_at,
            "updated_at": ku.updated_at,
            "last_used_at": ku.component.last_used_at,
        }
        ku_responses.append(KUResponse.model_validate(response_data))

    return api_list_response(
        ku_responses, total=total, request=request, pagination=pagination
    )


# --- Index Entry & Search Endpoints (Project Paros) ---
# Sub-resources of /indexes/{collection_id}


async def get_knowledge_index_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeIndexService:
    """Dependency injection for KnowledgeIndexService.

    Reuses the IntegrationService construction pattern from integrations router.
    """
    from analysi.routers.integrations import get_integration_service

    integration_service = await get_integration_service(session)
    return KnowledgeIndexService(session, integration_service)


@router.post(
    "/indexes/{collection_id}/entries",
    response_model=ApiResponse[AddEntriesResponse],
    status_code=201,
    dependencies=[Depends(require_permission("knowledge_units", "create"))],
)
async def add_index_entries(
    request: Request,
    collection_id: UUID,
    body: AddEntriesRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeIndexService, Depends(get_knowledge_index_service)],
) -> ApiResponse[AddEntriesResponse]:
    """Add entries to an index collection. Text is auto-embedded."""
    try:
        texts = [e.content for e in body.entries]
        metadata_list = [e.metadata for e in body.entries]
        source_refs = [e.source_ref for e in body.entries]

        entry_ids = await service.add_entries(
            tenant_id=tenant_id,
            collection_id=collection_id,
            texts=texts,
            metadata_list=metadata_list,
            source_refs=source_refs,
        )

        # Get collection for embedding_model info
        collection = await service.ku_repo.get_index_by_id(collection_id, tenant_id)

        response = AddEntriesResponse(
            entry_ids=entry_ids,
            collection_id=collection_id,
            entries_added=len(entry_ids),
            embedding_model=collection.embedding_model if collection else None,
        )
        return api_response(response, request=request)

    except EmbeddingModelMismatchError as e:
        logger.warning("embedding_model_mismatch", error=str(e))
        raise HTTPException(status_code=409, detail="Embedding model mismatch") from e
    except NoEmbeddingProviderError as e:
        logger.warning("no_embedding_provider", error=str(e))
        raise HTTPException(
            status_code=422,
            detail="No embedding-capable AI integration configured for this tenant",
        ) from e
    except CollectionNotFoundError as e:
        logger.warning("collection_not_found", error=str(e))
        raise HTTPException(status_code=404, detail="Collection not found") from e
    except ValueError as e:
        logger.warning("add_entries_validation_error", error=str(e))
        raise HTTPException(
            status_code=422, detail="Invalid embedding configuration"
        ) from e
    except Exception:
        logger.error("add_index_entries_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@router.post(
    "/indexes/{collection_id}/search",
    response_model=ApiResponse[SearchResponse],
    dependencies=[Depends(require_permission("knowledge_units", "read"))],
)
async def search_index(
    request: Request,
    collection_id: UUID,
    body: SearchRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeIndexService, Depends(get_knowledge_index_service)],
) -> ApiResponse[SearchResponse]:
    """Search an index collection by semantic similarity."""
    try:
        results = await service.search(
            tenant_id=tenant_id,
            collection_id=collection_id,
            query=body.query,
            top_k=body.top_k,
            score_threshold=body.score_threshold,
            metadata_filter=body.metadata_filter,
        )

        result_items = [
            SearchResultItem(
                entry_id=r.entry_id,
                content=r.content,
                score=r.score,
                metadata=r.metadata,
                source_ref=r.source_ref,
            )
            for r in results
        ]

        response = SearchResponse(
            results=result_items,
            query=body.query,
            collection_id=collection_id,
            total_results=len(result_items),
        )
        return api_response(response, request=request)

    except EmbeddingModelMismatchError as e:
        logger.warning("search_embedding_model_mismatch", error=str(e))
        raise HTTPException(status_code=409, detail="Embedding model mismatch") from e
    except NoEmbeddingProviderError as e:
        logger.warning("search_no_embedding_provider", error=str(e))
        raise HTTPException(
            status_code=422,
            detail="No embedding-capable AI integration configured for this tenant",
        ) from e
    except CollectionNotFoundError as e:
        logger.warning("search_collection_not_found", error=str(e))
        raise HTTPException(status_code=404, detail="Collection not found") from e
    except ValueError as e:
        logger.warning("search_validation_error", error=str(e))
        raise HTTPException(
            status_code=422, detail="Invalid embedding configuration"
        ) from e
    except Exception:
        logger.error("search_index_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@router.get(
    "/indexes/{collection_id}/entries",
    response_model=ApiListResponse[EntryResponse],
    dependencies=[Depends(require_permission("knowledge_units", "read"))],
)
async def list_index_entries(
    request: Request,
    collection_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeIndexService, Depends(get_knowledge_index_service)],
    pagination: PaginationParams = Depends(),
) -> ApiListResponse[EntryResponse]:
    """List entries in an index collection with pagination."""
    try:
        entries, total = await service.list_entries(
            tenant_id=tenant_id,
            collection_id=collection_id,
            offset=pagination.offset,
            limit=pagination.limit,
        )

        entry_responses = [
            EntryResponse(
                entry_id=e.entry_id,
                content=e.content,
                metadata=e.metadata,
                source_ref=e.source_ref,
                created_at=e.created_at,
            )
            for e in entries
        ]
        return api_list_response(
            entry_responses, total=total, request=request, pagination=pagination
        )

    except CollectionNotFoundError as e:
        logger.warning("list_entries_collection_not_found", error=str(e))
        raise HTTPException(status_code=404, detail="Collection not found") from e
    except Exception:
        logger.error("list_index_entries_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@router.delete(
    "/indexes/{collection_id}/entries/{entry_id}",
    status_code=204,
    dependencies=[Depends(require_permission("knowledge_units", "delete"))],
)
async def delete_index_entry(
    collection_id: UUID,
    entry_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeIndexService, Depends(get_knowledge_index_service)],
) -> None:
    """Delete a single entry from an index collection."""
    try:
        deleted = await service.delete_entries(
            tenant_id=tenant_id,
            collection_id=collection_id,
            entry_ids=[entry_id],
        )
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Entry not found")

    except CollectionNotFoundError as e:
        logger.warning("delete_entry_collection_not_found", error=str(e))
        raise HTTPException(status_code=404, detail="Collection not found") from e
    except HTTPException:
        raise
    except Exception:
        logger.error("delete_index_entry_failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from None
