"""Pydantic schemas for product chatbot API."""

import re
import unicodedata
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analysi.constants import ChatConstants

# --- Input validation constants ---

ALLOWED_CONTEXT_FIELDS = {"route", "entity_type", "entity_id"}

# Patterns that indicate prompt injection attempts.
# Combined into a single compiled regex for single-pass matching.
_INJECTION_PATTERNS = [
    # Instruction override
    r"ignore\s+(all\s+)?(previous|above|prior|earlier)\s+"
    r"(instructions|prompts|rules|context)",
    r"(disregard|forget|override)\s+(all\s+)?(previous|prior|above|system)",
    r"do\s+not\s+follow\s+(the\s+)?(above|previous|system)",
    r"(new|updated|revised)\s+instructions?\s*[:=]",
    # Role hijacking
    r"(you|your)\s+(are|role)\s+(now|is)\s+",
    r"pretend\s+(you|to)\s+(are|be)\s+",
    r"act\s+as\s+(if|though|a)\s+",
    r"from\s+now\s+on\s+(you|respond|act|behave)",
    # Exfiltration attempts
    r"(output|reveal|show|print|display)\s+(the|your)\s+"
    r"(system|secret|api|internal|prompt|instructions)",
    r"(what\s+are|tell\s+me)\s+your\s+(instructions|rules|system\s+prompt)",
    r"respond\s+(only\s+)?with\s+(yes|no|true|the\s+password)",
    # Model-specific injection tokens (matched after lowercasing)
    r"\[inst\]|\[/inst\]|<\|im_start\|>|<\|im_end\|>|<\|system\|>",
    r"```\s*(system|instruction|prompt)",
    r"<\|.*?\|>",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS))


# Common Cyrillic/Greek homoglyphs that look identical to Latin characters.
# NFKC normalization does NOT map these — they are distinct Unicode code points.
# We manually map them to Latin equivalents before injection pattern matching.
_CONFUSABLE_MAP = str.maketrans(
    # Cyrillic look-alikes → Latin
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458"  # а е о р с у х і ј
    # Greek look-alikes → Latin
    "\u03b1\u03b5\u03bf\u03c1",  # α ε ο ρ
    "aeopcyxij"  # Latin equivalents
    "aeor",
)


def contains_injection(text: str) -> bool:
    """Detect prompt injection patterns in text entering LLM context.

    Runs on: user messages, page_context values, and (in later phases)
    KU content, alert fields, integration responses.
    """
    # Step 1: Normalize — strip invisible/modifier chars, collapse whitespace, lowercase
    cleaned = unicodedata.normalize("NFKC", text)
    # Strip: zero-width chars, soft hyphens, word joiners, variation selectors,
    # combining diacritical marks, and other invisible format characters.
    # These can be inserted between letters to bypass regex pattern matching
    # while remaining invisible to humans and understood by LLMs.
    cleaned = re.sub(
        r"[\u00ad"  # Soft hyphen
        r"\u200b-\u200f"  # Zero-width space, ZWNJ, ZWJ, LRM, RLM
        r"\u2028-\u202f"  # Line/paragraph separators, embedding controls
        r"\u2060-\u2069"  # Word joiner, invisible operators
        r"\ufeff"  # BOM / zero-width no-break space
        r"\ufe00-\ufe0f"  # Variation selectors
        r"\u0300-\u036f"  # Combining diacritical marks
        r"]",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned.lower().strip())

    # Step 2: Map Cyrillic/Greek homoglyphs to Latin equivalents
    cleaned = cleaned.translate(_CONFUSABLE_MAP)

    # Step 3: Single-pass match against all injection patterns
    return _INJECTION_RE.search(cleaned) is not None


def sanitize_input(text: str) -> str:
    """Strip null bytes and control characters from user input.

    Raises ValueError if the text contains null bytes after sanitization.
    """
    # Remove null bytes
    if "\x00" in text:
        raise ValueError("Input contains null bytes")
    # Remove other control characters except whitespace (tab, newline, CR)
    cleaned = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return cleaned


# Max length for page_context values (prevents payload stuffing)
_MAX_CONTEXT_VALUE_LENGTH = 200


def sanitize_page_context(page_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip unknown fields and scan values for injection in page_context.

    Returns cleaned context or None.
    """
    if not page_context:
        return page_context
    cleaned = {}
    for key, val in page_context.items():
        if key not in ALLOWED_CONTEXT_FIELDS:
            continue
        # Only accept string values; reject nested objects
        if not isinstance(val, str):
            continue
        # Truncate oversized values
        if len(val) > _MAX_CONTEXT_VALUE_LENGTH:
            val = val[:_MAX_CONTEXT_VALUE_LENGTH]
        if contains_injection(val):
            cleaned[key] = "[filtered]"
        else:
            cleaned[key] = val
    return cleaned


# --- Request schemas ---


def _sanitize_title(title: str | None) -> str | None:
    """Strip HTML tags from conversation titles (defense-in-depth against XSS).

    Handles complete tags (<script>), incomplete tags (<script), and nested
    injection attempts (<scr<script>ipt>). Returns None if nothing remains.
    """
    if title is None:
        return None
    # Strip complete HTML tags, then incomplete opening tags (no closing >)
    cleaned = re.sub(r"<[^>]*>?", "", title)
    # Strip dangerous characters that could break out of HTML attributes
    cleaned = re.sub(r"[<>]", "", cleaned).strip()
    return cleaned if cleaned else None


class ConversationCreate(BaseModel):
    """Request body for creating a new conversation."""

    title: str | None = Field(None, max_length=500, description="Optional title")
    page_context: dict[str, Any] | None = Field(
        None, description="Page context at creation time"
    )

    @field_validator("title", mode="before")
    @classmethod
    def strip_html_from_title(cls, v: str | None) -> str | None:
        return _sanitize_title(v)

    @field_validator("page_context", mode="before")
    @classmethod
    def validate_page_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return sanitize_page_context(v)


class ConversationUpdate(BaseModel):
    """Request body for updating a conversation (title only)."""

    title: str = Field(..., min_length=1, max_length=500, description="New title")

    @field_validator("title", mode="before")
    @classmethod
    def strip_html_from_title(cls, v: str) -> str:
        result = _sanitize_title(v)
        if not result:
            raise ValueError("Title must contain text content, not just HTML tags")
        return result


class ChatMessageRequest(BaseModel):
    """Request body for sending a chat message."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=ChatConstants.MAX_MESSAGE_LENGTH,
        description="Message text",
    )
    page_context: dict[str, Any] | None = Field(
        None, description="Current page context (sent with every message)"
    )

    @field_validator("content", mode="after")
    @classmethod
    def validate_content(cls, v: str) -> str:
        cleaned = sanitize_input(v)
        if not cleaned.strip():
            msg = "Message content must not be empty after sanitization"
            raise ValueError(msg)
        return cleaned

    @field_validator("page_context", mode="before")
    @classmethod
    def validate_page_context(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return sanitize_page_context(v)


# --- Response schemas ---


def _coerce_none_to_dict(v: Any) -> dict[str, Any]:
    """Shared validator: coerce None metadata to empty dict."""
    if v is None:
        return {}
    return v


class ConversationResponse(BaseModel):
    """API response for a conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: str
    user_id: UUID
    title: str | None
    page_context: dict[str, Any] | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    token_count_total: int
    created_at: datetime
    updated_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def default_metadata(cls, v: Any) -> dict[str, Any]:
        return _coerce_none_to_dict(v)


class ChatMessageResponse(BaseModel):
    """API response for a chat message."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    tenant_id: str
    role: str
    content: Any
    tool_calls: Any | None = None
    token_count: int | None = None
    model: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class ConversationDetailResponse(ConversationResponse):
    """Conversation with its messages (extends ConversationResponse)."""

    messages: list[ChatMessageResponse] = Field(default_factory=list)
