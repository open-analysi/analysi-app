"""Knowledge Unit tools for product chatbot.

Provides read-only access to tenant Knowledge Units (documents, tables, indexes)
via Pydantic AI tool calls. All results are capped and scanned for injection.

Architecture:
  - Tools call KnowledgeUnitService directly (same process, not REST API)
  - Name-first lookup: the LLM uses human-readable names, not UUIDs
  - Tool results are capped at MAX_TOOL_RESULT_TOKENS to prevent context bloat
  - Injection patterns in KU content are flagged (tenant data is untrusted)
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.constants import ChatConstants
from analysi.schemas.chat import contains_injection
from analysi.services.knowledge_unit import KnowledgeUnitService

logger = get_logger(__name__)


# --- Tool result utilities ---


def cap_tool_result(text: str, max_tokens: int | None = None) -> str:
    """Truncate a tool result string to stay within the token budget.

    Uses the rough heuristic of ~4 characters per token.
    Reserves ~100 chars for the sanitize_tool_result XML wrapper
    that is applied after this function.
    Appends a [truncated] marker if the result was cut.
    """
    if max_tokens is None:
        max_tokens = ChatConstants.MAX_TOOL_RESULT_TOKENS
    # Reserve space for XML wrapper added by sanitize_tool_result (~100 chars)
    max_chars = max_tokens * 4 - 100
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated — result exceeded token limit]"


def sanitize_tool_result(text: str, source_description: str) -> str:
    """Scan a tool result for injection patterns and wrap with isolation notice.

    Tenant KU content is untrusted — it could contain prompt injection attempts.
    """
    if contains_injection(text):
        logger.warning(
            "chat_ku_injection_detected",
            source=source_description,
            content_preview=text[:200].replace("\n", "\\n"),
        )
        return (
            f"[Content from {source_description} was filtered by the safety system. "
            "The content contained patterns that could not be safely displayed.]"
        )

    return (
        f'<tool_result source="{source_description}" trust="user_content">\n'
        f"{text}\n"
        "</tool_result>"
    )


# --- KU tool implementations ---


async def search_knowledge(
    session: AsyncSession,
    tenant_id: str,
    query: str,
    ku_type: str | None = None,
    limit: int = 10,
) -> str:
    """Search tenant Knowledge Units by text query.

    Searches across names, descriptions, and categories of documents, tables,
    and indexes. Returns a summary of matching items.
    """
    service = KnowledgeUnitService(session)
    kus, meta = await service.search_kus(
        tenant_id=tenant_id,
        query=query,
        ku_type=ku_type,
        limit=min(limit, 20),  # Hard cap at 20 results
    )

    if not kus:
        return f"No Knowledge Units found matching '{query}'."

    lines = [
        f"Found {meta.get('total', len(kus))} Knowledge Units matching '{query}':\n"
    ]
    for ku in kus:
        component = ku.component if hasattr(ku, "component") else ku
        name = getattr(component, "name", "Unknown")
        description = getattr(component, "description", "")
        ku_type_val = getattr(ku, "ku_type", "unknown")
        status = getattr(component, "status", "unknown")
        categories = getattr(component, "categories", []) or []

        desc_preview = (
            description[:150] + "..." if len(description) > 150 else description
        )
        cat_str = f" [{', '.join(categories)}]" if categories else ""

        lines.append(f"- **{name}** ({ku_type_val}{cat_str}, {status}): {desc_preview}")

    result = "\n".join(lines)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, "knowledge unit search")


async def read_document(
    session: AsyncSession,
    tenant_id: str,
    name: str | None = None,
    document_id: str | None = None,
) -> str:
    """Read a specific KU document's content by name or ID.

    Returns the document's markdown content (preferred) or plain content.
    """
    service = KnowledgeUnitService(session)
    doc = await service.get_document_by_name_or_id(
        tenant_id=tenant_id, name=name, id=document_id
    )

    if doc is None:
        identifier = name or document_id or "unknown"
        return f"Document '{identifier}' not found."

    component = doc.component if hasattr(doc, "component") else doc
    doc_name = getattr(component, "name", "Unknown")

    # Prefer markdown content if available
    content = doc.markdown_content or doc.content or ""
    if not content:
        return f"Document '{doc_name}' exists but has no content."

    # Build result with metadata header
    lines = [
        f"# {doc_name}",
        f"Type: {getattr(doc, 'document_type', 'text')} | "
        f"Format: {getattr(doc, 'doc_format', 'text')}",
        "",
        content,
    ]

    result = "\n".join(lines)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"document '{doc_name}'")


async def read_table(
    session: AsyncSession,
    tenant_id: str,
    name: str | None = None,
    table_id: str | None = None,
    max_rows: int = 50,
) -> str:
    """Read a specific KU table's rows by name or ID.

    Returns a formatted representation of the table data.
    """
    service = KnowledgeUnitService(session)
    table = await service.get_table_by_name_or_id(
        tenant_id=tenant_id, name=name, id=table_id
    )

    if table is None:
        identifier = name or table_id or "unknown"
        return f"Table '{identifier}' not found."

    component = table.component if hasattr(table, "component") else table
    table_name = getattr(component, "name", "Unknown")

    # Extract rows from content
    content = table.content or {}
    rows: list[dict[str, Any]] = []
    if isinstance(content, dict):
        rows = content.get("rows", [])
    elif isinstance(content, list):
        rows = content

    if not rows:
        return f"Table '{table_name}' exists but has no data rows."

    # Apply row limit
    total_rows = len(rows)
    rows = rows[: min(max_rows, 100)]  # Hard cap at 100 rows

    # Format as JSON for readability
    lines = [
        f"# {table_name}",
        f"Rows: {total_rows} total"
        + (f" (showing first {len(rows)})" if len(rows) < total_rows else ""),
    ]

    # Include schema if available
    schema = table.schema if hasattr(table, "schema") else None
    if schema:
        lines.append(f"Schema: {json.dumps(schema)}")

    lines.append("")
    lines.append(json.dumps(rows, indent=2, default=str))

    result = "\n".join(lines)
    result = cap_tool_result(result)
    return sanitize_tool_result(result, f"table '{table_name}'")
