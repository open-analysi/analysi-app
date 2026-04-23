"""Product chatbot REST API endpoints.

Conversation CRUD + SSE streaming message endpoint.

API:
  POST   /{tenant}/chat/conversations                     Create conversation
  GET    /{tenant}/chat/conversations                     List conversations
  GET    /{tenant}/chat/conversations/{id}                Get conversation + messages
  PATCH  /{tenant}/chat/conversations/{id}                Update title
  DELETE /{tenant}/chat/conversations/{id}                Soft-delete
  POST   /{tenant}/chat/conversations/{id}/messages       Send message (SSE stream)
"""

import asyncio
import weakref
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
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
from analysi.config.logging import get_logger
from analysi.constants import ChatConstants
from analysi.db.session import AsyncSessionLocal, get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.conversation_repository import ConversationRepository
from analysi.schemas.activity_audit import ActorType, AuditSource
from analysi.schemas.chat import (
    ChatMessageRequest,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    ConversationUpdate,
)
from analysi.services.chat_service import ChatService, sse_done, sse_event

logger = get_logger(__name__)


# --- Dependencies ---


async def require_provisioned_user(
    current_user: CurrentUser = Depends(require_current_user),
) -> CurrentUser:
    """Require that the authenticated user has been provisioned (has a db_user_id).

    Chat requires a local database user record. Users without one (e.g.,
    freshly authenticated but not yet synced) get a 403.
    """
    if current_user.db_user_id is None:
        raise HTTPException(status_code=403, detail="User not provisioned")
    return current_user


# --- Audit helper ---


async def _log_chat_audit(
    session: AsyncSession,
    tenant_id: str,
    actor_id: UUID,
    action: str,
    resource_id: str,
    details: dict | None = None,
) -> None:
    """Record a chat audit event. Swallows exceptions to avoid breaking the caller."""
    try:
        repo = ActivityAuditRepository(session)
        await repo.create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type=ActorType.USER.value,
            source=AuditSource.REST_API.value,
            action=action,
            resource_type="conversation",
            resource_id=resource_id,
            details=details,
        )
    except Exception as exc:
        logger.warning("chat_audit_failed", error=str(exc)[:200])


# --- Per-conversation concurrency guard ---
# Prevents concurrent streams on the same conversation (mitigates token budget
# TOCTOU race and DB connection exhaustion). Uses WeakValueDictionary so locks
# are garbage-collected when no stream is active for a conversation.
_conversation_locks: weakref.WeakValueDictionary[UUID, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)
# Strong references kept while lock is in use (prevents GC during await)
_active_locks: dict[UUID, asyncio.Lock] = {}


def _get_conversation_lock(conversation_id: UUID) -> asyncio.Lock:
    """Get or create a per-conversation lock."""
    lock = _conversation_locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _conversation_locks[conversation_id] = lock
    return lock


# --- Router ---

router = APIRouter(
    prefix="/{tenant}/chat",
    tags=["chat"],
    dependencies=[Depends(require_permission("chat", "read"))],
)


# --- Conversation CRUD ---


@router.post(
    "/conversations",
    response_model=ApiResponse[ConversationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("chat", "create"))],
)
async def create_conversation(
    body: ConversationCreate,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_provisioned_user),
) -> ApiResponse[ConversationResponse]:
    """Create a new conversation."""
    repo = ConversationRepository(db)

    # Enforce per-user conversation cap
    _, existing_count = await repo.list_by_user(
        tenant_id=tenant, user_id=current_user.db_user_id, limit=1, offset=0
    )
    if existing_count >= ChatConstants.MAX_CONVERSATIONS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Conversation limit reached ({ChatConstants.MAX_CONVERSATIONS_PER_USER}). "
            "Delete old conversations to create new ones.",
        )

    conversation = await repo.create(
        tenant_id=tenant,
        user_id=current_user.db_user_id,
        title=body.title,
        page_context=body.page_context,
    )

    await _log_chat_audit(
        db,
        tenant,
        current_user.db_user_id,
        ChatConstants.AUDIT_CONVERSATION_CREATED,
        str(conversation.id),
    )

    return api_response(
        ConversationResponse.model_validate(conversation),
        request=request,
    )


@router.get(
    "/conversations",
    response_model=ApiListResponse[ConversationResponse],
)
async def list_conversations(
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_provisioned_user),
    pagination: PaginationParams = Depends(),
) -> ApiListResponse[ConversationResponse]:
    """List the current user's conversations."""
    repo = ConversationRepository(db)
    items, total = await repo.list_by_user(
        tenant_id=tenant,
        user_id=current_user.db_user_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return api_list_response(
        [ConversationResponse.model_validate(c) for c in items],
        total=total,
        request=request,
        pagination=pagination,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ApiResponse[ConversationDetailResponse],
)
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_provisioned_user),
) -> ApiResponse[ConversationDetailResponse]:
    """Get a conversation with its messages."""
    repo = ConversationRepository(db)
    conversation = await repo.get_by_id_with_messages(
        conversation_id, tenant, current_user.db_user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return api_response(
        ConversationDetailResponse.model_validate(conversation),
        request=request,
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ApiResponse[ConversationResponse],
    dependencies=[Depends(require_permission("chat", "update"))],
)
async def update_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_provisioned_user),
) -> ApiResponse[ConversationResponse]:
    """Update conversation title."""
    repo = ConversationRepository(db)
    conversation = await repo.update_title(
        conversation_id, tenant, current_user.db_user_id, body.title
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return api_response(
        ConversationResponse.model_validate(conversation),
        request=request,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    dependencies=[Depends(require_permission("chat", "delete"))],
)
async def delete_conversation(
    conversation_id: UUID,
    tenant: str = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_provisioned_user),
) -> None:
    """Soft-delete a conversation (hidden from list, retained for audit)."""
    repo = ConversationRepository(db)
    deleted = await repo.soft_delete(conversation_id, tenant, current_user.db_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


# --- Streaming message endpoint ---


@router.post(
    "/conversations/{conversation_id}/messages",
    dependencies=[Depends(require_permission("chat", "create"))],
)
async def send_message(
    conversation_id: UUID,
    body: ChatMessageRequest,
    request: Request,
    tenant: str = Depends(get_tenant_id),
    current_user: CurrentUser = Depends(require_provisioned_user),
) -> StreamingResponse:
    """Send a message and stream the assistant response via SSE.

    Note: This endpoint manages its own database session instead of using the
    get_db dependency. FastAPI tears down dependency generators when the response
    is returned, but SSE streaming needs the session alive for the full duration
    of the stream (to persist messages, update token counts, etc.).

    Returns text/event-stream. Each event is a JSON object:
      - {"type": "text_delta", "content": "..."}
      - {"type": "tool_call_start", "tool": "...", "input": {...}}
      - {"type": "tool_call_end", "tool": "...", "output": {...}}
      - {"type": "message_complete", "message_id": "...", "tokens": N}
      - {"type": "error", "message": "..."}
    Stream ends with: data: [DONE]
    """
    # Capture values needed inside the generator (avoid closure over mutable state)
    user_db_id = current_user.db_user_id
    user_roles = current_user.roles
    message_content = body.content
    page_context = body.page_context

    async def event_generator():
        """Stream SSE events with a dedicated database session.

        The session is created and managed here, not via get_db, because
        FastAPI closes dependency sessions before the response body is consumed.

        A per-conversation lock prevents concurrent streams on the same
        conversation (mitigates token budget TOCTOU and connection exhaustion).
        """
        lock = _get_conversation_lock(conversation_id)

        # Try to acquire — if another stream is active, reject immediately
        if lock.locked():
            yield sse_event(
                {
                    "type": "error",
                    "message": "Another message is already being processed in this conversation. Please wait.",
                }
            )
            yield sse_done()
            return

        # Hold a strong reference so the lock isn't GC'd while we await
        _active_locks[conversation_id] = lock
        try:
            async with lock:
                async with AsyncSessionLocal() as session:
                    try:
                        chat_service = ChatService(session)
                        message_completed = False
                        async for event in chat_service.send_message_stream(
                            conversation_id=conversation_id,
                            tenant_id=tenant,
                            user_id=user_db_id,
                            content=message_content,
                            page_context=page_context,
                            user_roles=user_roles,
                        ):
                            # Check if client disconnected
                            if await request.is_disconnected():
                                logger.info(
                                    "chat_client_disconnected",
                                    conversation_id=str(conversation_id),
                                )
                                break

                            # Track whether a message was fully processed
                            if '"type": "message_complete"' in event:
                                message_completed = True

                            yield event

                        # Audit trail — only when a message was actually processed
                        # (not on early exits: conversation not found, injection, budget)
                        if message_completed:
                            await _log_chat_audit(
                                session,
                                tenant,
                                user_db_id,
                                ChatConstants.AUDIT_MESSAGE_SENT,
                                str(conversation_id),
                                details={"message_length": len(message_content)},
                            )

                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        logger.error(
                            "chat_stream_generator_error",
                            error=str(exc)[:500],
                        )
                        yield sse_event({"type": "error", "message": "Internal error"})
                        yield sse_done()
        finally:
            _active_locks.pop(conversation_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
