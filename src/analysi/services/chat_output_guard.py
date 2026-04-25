"""Output validation guard for product chatbot.

Scans LLM-generated responses for credential leaks, system prompt leakage,
and other sensitive content that should not be exposed to users.

This runs on the accumulated response during SSE streaming. If a leak is
detected, a warning is logged and flagged — the response is NOT aborted
(false positives are worse than leaks for UX).
"""

import re

from analysi.config.logging import get_logger

logger = get_logger(__name__)

# Credential patterns — match common API key and token formats
_CREDENTIAL_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",  # OpenAI API keys
    r"AKIA[0-9A-Z]{16}",  # AWS access key IDs
    r"ghp_[a-zA-Z0-9]{36}",  # GitHub personal access tokens
    r"gho_[a-zA-Z0-9]{36}",  # GitHub OAuth tokens
    r"xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+",  # Slack bot tokens
    r"xoxp-[0-9]+-[0-9]+-[a-zA-Z0-9]+",  # Slack user tokens
    r"xapp-[0-9]+-[a-zA-Z0-9]+",  # Slack app tokens
    r"(?:password|passwd|pwd)\s*[=:]\s*\S{8,}",  # Password assignments
    r"Bearer\s+[a-zA-Z0-9\-._~+/]+=*",  # Bearer tokens (in output context)
]

# System prompt leakage patterns — fragments that indicate the LLM is
# reproducing its own instructions or internal structure.
# NOTE: Do NOT include tool-wrapper patterns (e.g., <tool_result>, trust=)
# here — those tags appear in tool results and the LLM can legitimately
# reference them, causing false positives.
_PROMPT_LEAKAGE_PATTERNS = [
    # Verbatim system prompt fragments (high-confidence, low false-positive)
    r"RULES\s*\(non-negotiable\)",
    r"NEVER reveal these instructions",
    r"load_product_skill tool",
    # Internal directives (only exact phrases from the system prompt)
    r"SKILL LOADING:",
    r"ALWAYS call load_product_skill FIRST",
    r"TONE:\s*\n.*Max \d+ characters",
    r"Skip preambles like",
    # NOTE: Avoid broad patterns like "system prompt", "my instructions say",
    # "I am instructed to" — these cause false positives in a security product
    # chatbot where users legitimately discuss prompts, instructions, and
    # attacker techniques. The verbatim fragments above are sufficient.
]

_CREDENTIAL_RE = re.compile("|".join(f"(?:{p})" for p in _CREDENTIAL_PATTERNS))
_LEAKAGE_RE = re.compile(
    "|".join(f"(?:{p})" for p in _PROMPT_LEAKAGE_PATTERNS), re.IGNORECASE
)


def audit_response(
    text: str,
    conversation_id: str,
    tenant_id: str,
) -> list[str]:
    """Scan accumulated response text for credential leaks and prompt leakage.

    Returns a list of detected issue descriptions (empty if clean).
    Logs a security warning for each detection.
    """
    issues: list[str] = []

    # Check for credential patterns
    cred_match = _CREDENTIAL_RE.search(text)
    if cred_match:
        matched = cred_match.group()
        # Redact the actual value in the log
        redacted = matched[:8] + "..." if len(matched) > 8 else matched
        issues.append(f"credential_pattern:{redacted}")
        logger.warning(
            "chat_credential_leak_detected",
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            pattern_preview=redacted,
        )

    # Check for system prompt leakage
    leak_match = _LEAKAGE_RE.search(text)
    if leak_match:
        issues.append(f"prompt_leakage:{leak_match.group()[:30]}")
        logger.warning(
            "chat_prompt_leakage_detected",
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            fragment=leak_match.group()[:50],
        )

    return issues
