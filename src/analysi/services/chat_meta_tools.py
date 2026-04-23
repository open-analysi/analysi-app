"""Meta tools for product chatbot.

Lightweight tools that provide contextual help without database or LLM calls.
"""

from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Page context → suggested prompts mapping
_PAGE_SUGGESTIONS: dict[str, list[str]] = {
    "alerts": [
        "Show me all high-severity alerts",
        "What is the disposition of the completed alerts?",
        "Have we seen any alerts with suspicious IPs?",
    ],
    "alert_detail": [
        "What is the disposition and confidence score for this alert?",
        "What IOCs are associated with this alert?",
        "What workflow should I run for this alert?",
    ],
    "workflows": [
        "List all workflows ranked by complexity",
        "How do I create a new workflow?",
        "Compare the SQL injection workflows",
    ],
    "workflow_detail": [
        "How many nodes does this workflow have?",
        "What tasks does this workflow use?",
        "How can I modify this workflow's nodes?",
    ],
    "tasks": [
        "List tasks by category",
        "How do I write a Cy script for a new task?",
        "Which tasks use Splunk?",
    ],
    "task_detail": [
        "Explain what this task does",
        "What function type is this task?",
        "What categories does this task belong to?",
    ],
    "integrations": [
        "Which integrations are healthy and which are not?",
        "Which integrations support the ThreatIntel archetype?",
        "How do I add a new integration?",
    ],
    "knowledge_units": [
        "What Knowledge Units are available?",
        "Search knowledge base for Splunk tools",
        "How do I upload a new knowledge document?",
    ],
    "dashboard": [
        "Give me a platform overview with alerts and integration health",
        "How many tasks do we have by function type?",
        "Are all integrations healthy?",
    ],
    "admin": [
        "Show recent audit trail events",
        "What roles are available?",
        "How do I manage user roles?",
    ],
}

# Default suggestions when page context is unknown
_DEFAULT_SUGGESTIONS = [
    "What can you help me with?",
    "Show me the platform overview",
    "How do I analyze an alert?",
    "Which integrations are healthy?",
]


def get_page_context_impl(page_context: dict[str, Any] | None) -> str:
    """Return structured info about the current page the user is on."""
    if not page_context:
        return "No page context available. The user may be on the dashboard or haven't navigated yet."

    lines = ["Current page context:\n"]
    for key, value in page_context.items():
        lines.append(f"- **{key}**: {value}")

    return "\n".join(lines)


def suggest_next_steps_impl(page_context: dict[str, Any] | None) -> str:
    """Return contextual follow-up prompt suggestions. Template-based, no LLM call."""
    page = "dashboard"
    if page_context:
        # Extract page type from context.
        # Uses ALLOWED_CONTEXT_FIELDS: "route" for URL path, "entity_type" for page type.
        path = page_context.get("route", "")
        page_type = page_context.get("entity_type", "")

        if page_type:
            page = page_type
        elif "/alerts/" in path:
            page = "alert_detail"
        elif "/alerts" in path:
            page = "alerts"
        elif "/workflows/" in path:
            page = "workflow_detail"
        elif "/workflows" in path:
            page = "workflows"
        elif "/tasks/" in path:
            page = "task_detail"
        elif "/tasks" in path:
            page = "tasks"
        elif "/integrations" in path:
            page = "integrations"
        elif "/knowledge" in path:
            page = "knowledge_units"
        elif "/admin" in path:
            page = "admin"

    suggestions = _PAGE_SUGGESTIONS.get(page, _DEFAULT_SUGGESTIONS)

    lines = ["Here are some things you can ask me:\n"]
    for s in suggestions:
        lines.append(f"- {s}")

    return "\n".join(lines)
