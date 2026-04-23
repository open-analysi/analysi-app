"""Chat service — orchestrates conversation flow and LLM agent invocation.

Responsibilities:
  - Validate and persist user messages
  - Enforce per-conversation token budget
  - Build conversation history with message/token caps
  - Build system prompt with security rules + overview + pinned skills
  - Pre-load domain skills from page context
  - Register load_product_skill and KU tools on the Pydantic AI agent
  - Enforce tool call cap per turn
  - Invoke Pydantic AI agent and stream the response
  - Scan output for credential leaks and prompt leakage
  - Persist assistant messages with token/latency metrics
  - Track pinned skills in conversation metadata
  - Record security audit events for injection detection
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.agent import ModelRequestNode
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.permissions import has_permission
from analysi.config.logging import get_logger
from analysi.constants import ChatConstants
from analysi.models.conversation import ChatMessage
from analysi.repositories.chat_message_repository import ChatMessageRepository
from analysi.repositories.conversation_repository import ConversationRepository
from analysi.schemas.chat import contains_injection
from analysi.services.chat_action_tools import (
    PendingAction,
)
from analysi.services.chat_model_resolver import resolve_chat_model
from analysi.services.chat_output_guard import audit_response
from analysi.services.chat_skills import (
    AVAILABLE_SKILLS,
    build_system_prompt,
    get_preloaded_skill,
    update_pinned_skills,
)

logger = get_logger(__name__)

# Rough token estimator for history cap (same heuristic as skill budgets)
_CHARS_PER_TOKEN = 4


@dataclass
class ChatDeps:
    """Dependencies injected into Pydantic AI agent tool calls.

    The pinned_skills list is mutable — modified by load_product_skill during
    agent execution, then read by the service after stream completion to persist.
    tool_call_count tracks non-exempt tool calls for the per-turn cap.
    """

    tenant_id: str
    user_id: UUID
    user_roles: list[str]  # From JWT — used for role-gated tools
    conversation_id: UUID
    session: AsyncSession  # DB session for KU tool queries
    page_context: dict[str, Any] | None = None  # Current page info for meta tools
    # Mutable: updated by load_product_skill tool during agent execution
    pinned_skills: list[str] = field(default_factory=list)
    # Mutable: incremented by non-exempt tool calls for per-turn cap
    tool_call_count: int = 0
    # Mutable: tracks skill loads per turn (capped at MAX_PINNED_SKILLS)
    skill_load_count: int = 0
    # Mutable: pending action awaiting user confirmation (persisted in conversation metadata)
    pending_action: PendingAction | None = None


def check_chat_action_permission(
    user_roles: list[str],
    resource: str,
    action: str,
) -> str | None:
    """Check if the user's roles grant a specific permission.

    Used by chat action tools to enforce RBAC before executing mutations.
    Returns an error message if denied, None if allowed.
    """
    if has_permission(user_roles, resource, action):
        return None
    return (
        f"This action requires {resource}.{action} permission. "
        "Your current role does not have access."
    )


def _check_tool_call_limit(deps: ChatDeps) -> str | None:
    """Check if the tool call cap has been reached.

    Returns an error message if exceeded, None if OK.
    Only increments the counter on success (so rejected calls don't inflate it).
    """
    if deps.tool_call_count >= ChatConstants.MAX_TOOL_CALLS_PER_TURN:
        return (
            f"Tool call limit reached ({ChatConstants.MAX_TOOL_CALLS_PER_TURN} "
            "per turn). Please ask your question and I'll answer with "
            "the information already gathered."
        )
    deps.tool_call_count += 1
    return None


def _build_agent(model: str | Model, system_prompt: str) -> Agent[ChatDeps]:
    """Build a Pydantic AI agent with tools from the registry.

    All 22 tools are defined in chat_tool_registry.py. This function just
    assembles the agent with the system prompt and tool list.
    """
    from analysi.services.chat_tool_registry import build_tool_list

    return Agent(
        model,
        system_prompt=system_prompt,
        deps_type=ChatDeps,
        tools=build_tool_list(),
    )


async def _stream_agent_response(
    agent: Agent[ChatDeps],
    content: str,
    deps: ChatDeps,
    message_history: list[ModelMessage],
    model_settings: dict[str, Any] | None,
) -> AsyncGenerator[tuple[str, int]]:
    """Run the agent with iter() and yield (chunk, 0) for text deltas.

    After all nodes complete, yields ("", total_tokens) as the final item.
    Using iter() instead of run_stream() ensures tool calls execute and the
    agent continues generating text after tool results are returned.

    Streaming strategy:
      All ModelRequestNode text is streamed in real-time — the user sees
      tokens arrive word-by-word. Tool call execution emits structured
      events so the UI can show a "looking up..." indicator. This matches
      ChatGPT/Claude.ai UX where the user sees status during tool calls.

    Yields:
      - ("text_delta:...", 0) for text chunks
      - ("tool_call_start:...", 0) for tool call start (JSON payload)
      - ("tool_call_end:...", 0) for tool call end (JSON payload)
      - ("", total_tokens) as the final item
    """
    from pydantic_ai.agent import CallToolsNode as _CallToolsNode
    from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent
    from pydantic_ai.usage import UsageLimits

    # Cap LLM round-trips to prevent tool-call loops.
    # Default is 50 — too high for a product chatbot.
    _MAX_AGENT_REQUESTS = 12

    async with agent.iter(
        content,
        deps=deps,
        message_history=message_history,
        model_settings=model_settings if model_settings else None,
        usage_limits=UsageLimits(request_limit=_MAX_AGENT_REQUESTS),
    ) as agent_run:
        async for node in agent_run:
            if isinstance(node, _CallToolsNode):
                # Stream tool call events so the UI shows progress
                async with node.stream(agent_run.ctx) as events:
                    async for event in events:
                        if isinstance(event, FunctionToolCallEvent):
                            yield (
                                f"tool_call_start:{json.dumps({'tool': event.part.tool_name})}",
                                0,
                            )
                        elif isinstance(event, FunctionToolResultEvent):
                            yield (
                                f"tool_call_end:{json.dumps({'tool': event.result.tool_name})}",
                                0,
                            )

            elif isinstance(node, ModelRequestNode):
                # Stream all text in real-time — no buffering
                async with node.stream(agent_run.ctx) as agent_stream:
                    async for chunk in agent_stream.stream_text(delta=True):
                        yield (chunk, 0)

        usage = agent_run.usage()
        total_tokens = (
            (usage.request_tokens or 0) + (usage.response_tokens or 0) if usage else 0
        )
        yield ("", total_tokens)


class ChatService:
    """Service layer for chat operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.conversation_repo = ConversationRepository(session)
        self.message_repo = ChatMessageRepository(session)

    async def send_message_stream(  # noqa: C901
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: UUID,
        content: str,
        page_context: dict[str, Any] | None = None,
        user_roles: list[str] | None = None,
    ) -> AsyncGenerator[str]:
        """Process a user message and stream the assistant response as SSE events.

        Yields SSE-formatted strings: "data: {...}\\n\\n"
        """
        # 1. Verify conversation ownership
        conversation = await self.conversation_repo.get_by_id(
            conversation_id, tenant_id, user_id
        )
        if conversation is None:
            yield sse_event({"type": "error", "message": "Conversation not found"})
            yield sse_done()
            return

        # 2. Enforce per-conversation token budget
        if (
            conversation.token_count_total
            >= ChatConstants.CONVERSATION_LIFETIME_TOKEN_BUDGET
        ):
            yield sse_event(
                {
                    "type": "text_delta",
                    "content": (
                        "This conversation has reached its token limit "
                        f"({ChatConstants.CONVERSATION_LIFETIME_TOKEN_BUDGET:,} tokens). "
                        "Please start a new conversation to continue."
                    ),
                }
            )
            yield sse_event({"type": "message_complete", "tokens": 0})
            yield sse_done()
            return

        # 3. Check for injection in user message
        if contains_injection(content):
            logger.warning(
                "chat_injection_detected",
                tenant_id=tenant_id,
                user_id=str(user_id),
                conversation_id=str(conversation_id),
                content_preview=content[:200].replace("\n", "\\n"),
            )
            yield sse_event(
                {
                    "type": "text_delta",
                    "content": (
                        "I can only help with Analysi product questions. "
                        "Your message was flagged by our safety system."
                    ),
                }
            )
            yield sse_event({"type": "message_complete", "tokens": 0})
            yield sse_done()
            return

        # 4. Persist user message
        await self.message_repo.create(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=ChatConstants.Role.USER,
            content={"text": content},
        )

        # 5. Build conversation history with message + token caps
        messages_db = await self.message_repo.list_recent_by_conversation(
            conversation_id, tenant_id, limit=ChatConstants.MAX_HISTORY_MESSAGES
        )
        message_history = _build_message_history(
            messages_db, max_tokens=ChatConstants.MAX_HISTORY_TOKENS
        )

        # 6. Load pinned skills from conversation metadata (filter stale names)
        metadata = conversation.metadata_ or {}
        pinned_skills: list[str] = [
            s for s in metadata.get("loaded_skills", []) if s in AVAILABLE_SKILLS
        ]

        # 7. Pre-load skill from page context (if not already pinned)
        preload_skill = get_preloaded_skill(page_context)
        if preload_skill and preload_skill not in pinned_skills:
            pinned_skills = update_pinned_skills(pinned_skills, preload_skill)

        # 8. Build system prompt with current pinned skills
        system_prompt = build_system_prompt(pinned_skills)

        # 9. Resolve model via integrations framework (credentials from Vault)
        try:
            model, model_settings = await resolve_chat_model(
                tenant_id=tenant_id,
                session=self.session,
                capability="default",
            )
        except ValueError as exc:
            error_msg = str(exc)
            is_no_provider = "No AI provider configured" in error_msg
            code = "no_ai_provider" if is_no_provider else "ai_provider_error"
            logger.error("chat_model_resolution_failed", error=error_msg, code=code)
            if is_no_provider:
                message = (
                    "No AI integration configured. "
                    "Set up an OpenAI, Anthropic, or Gemini integration "
                    "with API credentials to use the chat assistant."
                )
            else:
                message = (
                    "AI integration credentials are misconfigured. "
                    "Check your AI integration settings and API key credentials."
                )
            yield sse_event({"type": "error", "code": code, "message": message})
            yield sse_done()
            return

        agent = _build_agent(model, system_prompt)

        # Restore pending action from conversation metadata (cross-turn persistence)
        pending_action = None
        pending_data = metadata.get("pending_action")
        if pending_data:
            try:
                pending_action = PendingAction.from_dict(pending_data)
            except (KeyError, TypeError):
                pending_action = None

        deps = ChatDeps(
            tenant_id=tenant_id,
            user_id=user_id,
            user_roles=user_roles or [],
            conversation_id=conversation_id,
            session=self.session,
            page_context=page_context,
            pinned_skills=pinned_skills,
            pending_action=pending_action,
        )

        # 10. Stream agent response with timeout + output guard
        start_time = time.monotonic()
        accumulated_chunks: list[str] = []
        total_tokens = 0
        stream_succeeded = False
        output_issues: list[str] = []

        try:
            async with asyncio.timeout(ChatConstants.STREAM_TIMEOUT_SECONDS):
                async for chunk, tokens in _stream_agent_response(
                    agent, content, deps, message_history, model_settings
                ):
                    if chunk:
                        # Tool call events use a prefix protocol
                        if chunk.startswith("tool_call_start:"):
                            payload = json.loads(chunk[len("tool_call_start:") :])
                            yield sse_event({"type": "tool_call_start", **payload})
                        elif chunk.startswith("tool_call_end:"):
                            payload = json.loads(chunk[len("tool_call_end:") :])
                            yield sse_event({"type": "tool_call_end", **payload})
                        else:
                            accumulated_chunks.append(chunk)
                            yield sse_event({"type": "text_delta", "content": chunk})
                    if tokens:
                        total_tokens = tokens
                stream_succeeded = True
        except TimeoutError:
            logger.warning(
                "chat_stream_timeout",
                conversation_id=str(conversation_id),
                elapsed_seconds=ChatConstants.STREAM_TIMEOUT_SECONDS,
            )
            yield sse_event(
                {
                    "type": "error",
                    "message": "Response timed out",
                }
            )
        except Exception as exc:
            logger.error(
                "chat_stream_error",
                conversation_id=str(conversation_id),
                error=str(exc)[:500],
            )
            yield sse_event(
                {
                    "type": "error",
                    "message": "An error occurred while generating the response",
                }
            )

        # 11. Output guard — scan response for leaks (even on partial streams,
        #     since text_delta chunks were already sent to the client)
        accumulated_text = "".join(accumulated_chunks)
        if accumulated_text:
            output_issues = audit_response(
                accumulated_text,
                conversation_id=str(conversation_id),
                tenant_id=tenant_id,
            )

        # 12. Persist assistant message (only on successful stream completion)
        latency_ms = int((time.monotonic() - start_time) * 1000)
        if stream_succeeded and accumulated_text:
            assistant_msg = await self.message_repo.create(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                role=ChatConstants.Role.ASSISTANT,
                content={"text": accumulated_text},
                token_count=total_tokens if total_tokens > 0 else None,
                model=model.model_name if isinstance(model, Model) else str(model),
                latency_ms=latency_ms,
            )

            # 13. Update conversation token count
            if total_tokens > 0:
                await self.conversation_repo.increment_token_count(
                    conversation_id, tenant_id, total_tokens
                )

            yield sse_event(
                {
                    "type": "message_complete",
                    "message_id": str(assistant_msg.id),
                    "tokens": total_tokens,
                    **({"security_flags": output_issues} if output_issues else {}),
                }
            )

        # 14. Persist updated pinned skills (may have changed via tool calls)
        if deps.pinned_skills != list(metadata.get("loaded_skills", [])):
            await self.conversation_repo.update_loaded_skills(
                conversation_id, tenant_id, deps.pinned_skills
            )

        # 15. Persist pending_action for cross-turn confirmation flow
        new_pending = deps.pending_action.to_dict() if deps.pending_action else None
        old_pending = metadata.get("pending_action")
        if new_pending != old_pending:
            await self.conversation_repo.update_metadata_field(
                conversation_id, tenant_id, "pending_action", new_pending
            )

        yield sse_done()


def _get_message_text(msg: ChatMessage) -> str:
    """Extract text content from a stored chat message.

    Handles both dict ({"text": "..."}) and raw string content formats.
    Defensive against {"text": null} in JSONB.
    """
    if isinstance(msg.content, dict):
        return msg.content.get("text", "") or ""
    if isinstance(msg.content, str):
        return msg.content
    return ""


def _estimate_message_tokens(msg: ChatMessage) -> int:
    """Rough token estimate for a stored message."""
    return len(_get_message_text(msg)) // _CHARS_PER_TOKEN


def _build_message_history(
    messages: list[ChatMessage],
    max_tokens: int | None = None,
) -> list[ModelMessage]:
    """Convert stored messages to Pydantic AI message history format.

    Excludes the most recent user message (it's passed separately to run_stream).
    Applies token cap: drops oldest messages first if history exceeds max_tokens.
    Re-scans user messages for injection (tenant content could be poisoned).
    Assistant messages are not re-scanned — the LLM cannot inject itself.
    """
    # Exclude the last message (it's the current user message)
    past_messages = messages[:-1] if messages else []

    # Apply token cap — drop oldest messages until under budget
    if max_tokens and past_messages:
        total_tokens = sum(_estimate_message_tokens(m) for m in past_messages)
        while total_tokens > max_tokens and len(past_messages) > 1:
            dropped = past_messages.pop(0)
            total_tokens -= _estimate_message_tokens(dropped)

    history: list[ModelMessage] = []

    for msg in past_messages:
        content_text = _get_message_text(msg)

        # Re-scan user messages for injection (defense-in-depth against
        # DB tampering). Assistant messages are not re-scanned — the LLM
        # cannot inject itself, and output is already covered by audit_response.
        if msg.role == ChatConstants.Role.USER and contains_injection(content_text):
            content_text = "[Message filtered by safety system]"

        if msg.role == ChatConstants.Role.USER:
            history.append(ModelRequest(parts=[UserPromptPart(content=content_text)]))
        elif msg.role == ChatConstants.Role.ASSISTANT:
            history.append(ModelResponse(parts=[TextPart(content=content_text)]))

    return history


def sse_event(data: dict[str, Any]) -> str:
    """Format a dict as an SSE event string."""
    return f"data: {json.dumps(data)}\n\n"


def sse_done() -> str:
    """Format the SSE stream terminator."""
    return "data: [DONE]\n\n"
