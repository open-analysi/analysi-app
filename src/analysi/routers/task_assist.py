"""Task authoring assistance endpoints (autocomplete, etc.)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import ApiResponse, api_response
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.services.cy_autocomplete import get_cy_completions

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/tasks",
    tags=["task-assist"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)
# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AutocompleteRequest(BaseModel):
    """Request body for Cy script autocomplete."""

    script_prefix: str = Field(
        description="Script content before the cursor (what the LLM continues from)"
    )
    script_suffix: str = Field(
        default="",
        description="Script content after the cursor (optional context)",
    )
    trigger_kind: Literal["invoked", "character", "newline"] = Field(
        default="invoked",
        description="Why autocomplete was triggered",
    )
    trigger_character: str | None = Field(
        default=None,
        description="The character that triggered completion (e.g. '.', ':', '(')",
    )


class CompletionItem(BaseModel):
    """A single completion suggestion."""

    insert_text: str = Field(description="Text to insert at the cursor")
    label: str = Field(description="Display text in the dropdown")
    detail: str = Field(default="", description="Short description alongside the label")
    kind: Literal["function", "keyword", "variable", "field", "snippet"] = Field(
        default="snippet"
    )


class AutocompleteResponse(BaseModel):
    """Response for Cy script autocomplete."""

    completions: list[CompletionItem]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/autocomplete", response_model=ApiResponse[AutocompleteResponse])
async def autocomplete_cy_script(
    body: AutocompleteRequest,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[AutocompleteResponse]:
    """Return LLM-generated completions for a partial Cy script.

    Loads the cy-language-programming skill from the database and calls the
    configured primary LLM to generate 1-5 completion suggestions.
    """
    try:
        completions_raw = await get_cy_completions(
            tenant_id=tenant_id,
            session=session,
            script_prefix=body.script_prefix,
            script_suffix=body.script_suffix or None,
            trigger_kind=body.trigger_kind,
            trigger_character=body.trigger_character,
        )
    except ValueError as exc:
        logger.error("autocomplete_config_error", error=str(exc))
        raise HTTPException(
            status_code=422, detail="Autocomplete service not configured"
        ) from exc
    except Exception as exc:
        logger.exception("autocomplete_failed")
        raise HTTPException(
            status_code=500, detail="Autocomplete service error"
        ) from exc

    items = [CompletionItem(**c) for c in completions_raw]
    return api_response(AutocompleteResponse(completions=items), request=request)
