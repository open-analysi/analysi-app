"""Cy language autocomplete service.

Uses the cy-language-programming skill (loaded from DB), the tenant's real
tool registry, and a golden example task to generate accurate completion
suggestions for the Cy script editor.

Performance budget per request (warm cache, character trigger):
  - Skill:    ~4 KB  (first 4 KB for character; full 21 KB for invoked/newline)
  - Tools:    ~0.5 KB  (context-filtered: only tools matching cursor namespace)
  - Example:  0 KB  (skipped for character triggers)
  - User msg: ~0.2 KB
  Total: ~5 KB  →  target <2s on gpt-4o-mini
"""

import json
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.agentic_orchestration.langgraph.config import get_db_skills_store
from analysi.config.logging import get_logger
from analysi.models.component import Component, ComponentKind
from analysi.models.task import Task
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.services.cy_tool_registry import load_tool_registry_async
from analysi.services.integration_service import IntegrationService
from analysi.services.llm_factory import LangChainFactory
from analysi.services.vault_client import VaultClient

logger = get_logger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

CY_SKILL_NAME = "cy-language-programming"
CY_SKILL_FILE = "SKILL.md"

GOLDEN_TASK_NAME = "VirusTotal: IP Reputation Analysis"
GOLDEN_FALLBACK_MIN_LINES = 10

CACHE_TTL = 60.0  # seconds

# Skill chars included per trigger type.
# character trigger: just the top of SKILL.md (syntax + native functions overview)
# invoked / newline: full skill for richer context
SKILL_CHARS_BY_TRIGGER: dict[str, int | None] = {
    "character": 4000,
    "invoked": None,  # full
    "newline": None,  # full
}

# Max app:: tool lines when no specific namespace is detected in the prefix.
DEFAULT_APP_TOOL_CAP = 20

# ── in-process caches (per tenant) ────────────────────────────────────────────
_skill_cache: dict[str, tuple[str | None, float]] = {}
# Full registry dict cached; filtering happens at request time
_registry_cache: dict[str, tuple[dict[str, Any], float]] = {}
_example_cache: dict[str, tuple[str | None, float]] = {}

# ── Cy keyword fast-path snippets ─────────────────────────────────────────────
# When the cursor is on a complete Cy keyword, return these immediately without
# an LLM call — faster and immune to the LLM defaulting to Python syntax.
_CY_KEYWORD_SNIPPETS: dict[str, list[dict[str, Any]]] = {
    "for": [
        {
            "insert_text": " (item in items) {\n    \n}",
            "label": "for (item in items) { }",
            "detail": "For-in loop",
            "kind": "keyword",
        },
    ],
    "if": [
        {
            "insert_text": " (condition) {\n    \n}",
            "label": "if (condition) { }",
            "detail": "Conditional block",
            "kind": "keyword",
        },
        {
            "insert_text": " (condition) {\n    \n} else {\n    \n}",
            "label": "if (condition) { } else { }",
            "detail": "If-else block",
            "kind": "keyword",
        },
    ],
    "elif": [
        {
            "insert_text": " (condition) {\n    \n}",
            "label": "elif (condition) { }",
            "detail": "Else-if branch",
            "kind": "keyword",
        },
    ],
    "else": [
        {
            "insert_text": " {\n    \n}",
            "label": "else { }",
            "detail": "Else branch",
            "kind": "keyword",
        },
    ],
    "while": [
        {
            "insert_text": " (condition) {\n    \n}",
            "label": "while (condition) { }",
            "detail": "While loop",
            "kind": "keyword",
        },
    ],
    "try": [
        {
            "insert_text": ' {\n    \n} catch (e) {\n    log("Error: ${e}")\n}',
            "label": "try { } catch (e) { }",
            "detail": "Error handling block",
            "kind": "keyword",
        },
    ],
    "return": [
        {
            "insert_text": " result",
            "label": "return result",
            "detail": "Return a value",
            "kind": "keyword",
        },
        {
            "insert_text": ' {"status": "ok"}',
            "label": "return { }",
            "detail": "Return a dict",
            "kind": "keyword",
        },
    ],
}


def _cursor_inside_string(script_prefix: str) -> bool:
    """Return True if the cursor appears to be inside an open single-line string literal.

    Checks the last line of the prefix for an odd number of unescaped double-quote
    characters after stripping out completed triple-quoted and single-quoted sections.
    We suppress completions in this case — the LLM would otherwise inject code
    templates as string content.
    """
    last_line = script_prefix.rsplit("\n", 1)[-1]
    # Remove escaped quotes so they don't skew the count
    cleaned = last_line.replace('\\"', "")
    # Remove completed triple-quoted sections
    cleaned = re.sub(r'""".*?"""', "", cleaned)
    # Remove completed single-quoted sections (double-quoted pairs)
    cleaned = re.sub(r'"[^"]*"', "", cleaned)
    # An odd number of remaining quotes means we're inside an open string
    return cleaned.count('"') % 2 == 1


def _get_keyword_completions(
    script_prefix: str, trigger_kind: str, trigger_character: str | None
) -> list[dict[str, Any]] | None:
    """Return hardcoded Cy keyword snippets if the cursor is on a complete keyword.

    Return values:
      - Non-empty list  → cursor completes a known Cy keyword; use these snippets
      - Empty list []   → cursor is inside "keyword(" — suppress all completions
                          (the editor has auto-inserted a matching ')' in the suffix;
                          any insert_text we generate would produce an extra ')')
      - None            → not a keyword context; fall through to the LLM
    """
    # Detect "keyword(" pattern: prefix ends with a keyword immediately followed by '('.
    # In this case the editor has auto-closed with ')' in the suffix — suppress.
    keyword_open_paren = re.search(r"\b(\w+)\($", script_prefix)
    if (
        keyword_open_paren
        and keyword_open_paren.group(1).lower() in _CY_KEYWORD_SNIPPETS
    ):
        return []

    # Allow trailing whitespace so "if " (after pressing space) still hits the fast-path.
    last_word_match = re.search(r"([\w]+)\s*$", script_prefix)
    prefix_fragment = last_word_match.group(1) if last_word_match else ""

    if (
        trigger_kind == "character"
        and trigger_character
        and trigger_character.isalpha()
    ):
        fragment = prefix_fragment + trigger_character
    else:
        fragment = prefix_fragment

    return _CY_KEYWORD_SNIPPETS.get(fragment.lower()) if fragment else None


# ── prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
You are a Cy language autocomplete engine. Cy is a custom scripting language for security automation tasks.

Here is the Cy language reference:

<cy_skill>
{skill_content}
</cy_skill>

{tools_section}\
{example_section}\
Rules:
- Generate 1-5 completions for what comes immediately after the cursor.
- ONLY suggest tools that appear in <available_tools> — never invent tool names.
- insert_text is ONLY the suffix to splice at the cursor position:
    • If partial identifier is "llm_r", insert_text is "un(" — not "llm_run("
    • If partial identifier is "enrich_", insert_text is "alert(" — not "enrich_alert("
    • If partial identifier is "app::abuseipdb::", insert_text is "lookup_ip(ip=" — not "app::abuseipdb::lookup_ip(ip="
- For function/tool calls: use the parameter names from <available_tools>, not invented names.
- For field completions: label should be just the field name (e.g. "severity"), not "alert.severity".
- kind values: function | keyword | variable | field | snippet
- Return a JSON array only, no markdown, no explanation:
  [{{"insert_text":"...","label":"...","detail":"...","kind":"..."}}]\
"""

_TOOLS_SECTION_TEMPLATE = """\
Available tools (use ONLY these FQNs):

<available_tools>
{tool_lines}
</available_tools>

"""

_EXAMPLE_SECTION_TEMPLATE = """\
Golden example of a well-written Cy task (mirror this style):

<example_task>
```cy
{example_script}
```
</example_task>

"""

_USER_PROMPT_TEMPLATE = """\
Script so far:
```cy
{script_prefix}
```
{suffix_section}
Trigger: {trigger_kind}{trigger_char_section}
{partial_word_hint}
Completions:\
"""


# ── skill loading ─────────────────────────────────────────────────────────────


async def _load_skill_content(tenant_id: str) -> str | None:
    now = time.monotonic()
    cached = _skill_cache.get(tenant_id)
    if cached is not None and now - cached[1] < CACHE_TTL:
        return cached[0]

    store = get_db_skills_store(tenant_id)
    content = await store.read_async(CY_SKILL_NAME, CY_SKILL_FILE)
    _skill_cache[tenant_id] = (content, now)
    if content:
        logger.debug(
            "Loaded skill %s for tenant %s (%d chars)",
            CY_SKILL_FILE,
            tenant_id,
            len(content),
        )
    else:
        logger.warning(
            "Skill %s/%s not found in DB for tenant %s — completions will lack language context",
            CY_SKILL_NAME,
            CY_SKILL_FILE,
            tenant_id,
        )
    return content


# ── tool registry loading & context-aware filtering ──────────────────────────


async def _load_registry(tenant_id: str, session: AsyncSession) -> dict[str, Any]:
    """Load and cache the full tool registry dict."""
    now = time.monotonic()
    cached = _registry_cache.get(tenant_id)
    if cached is not None and now - cached[1] < CACHE_TTL:
        return cached[0]

    try:
        registry = await load_tool_registry_async(session, tenant_id)
        logger.debug("Loaded %d tools for tenant %s", len(registry), tenant_id)
    except Exception:
        logger.warning(
            "Failed to load tool registry for tenant %s — completions may suggest invalid tools",
            tenant_id,
            exc_info=True,
        )
        registry = {}

    _registry_cache[tenant_id] = (registry, now)
    return registry


def _filter_tools_for_context(registry: dict[str, Any], prefix: str) -> list[str]:
    """Return tool summary lines relevant to the cursor context.

    Detects three contexts from the last line of the prefix:
    1. app::<ns>:: typed → only that integration's tools
    2. llm_ / native:: typed → only native tools
    3. Anything else → all native tools + top DEFAULT_APP_TOOL_CAP app tools
    """
    last_line = prefix.split("\n")[-1] if "\n" in prefix else prefix

    # Context 1: explicit integration namespace
    app_ns_match = re.search(r"app::(\w+)::?$", last_line)
    if app_ns_match:
        ns = app_ns_match.group(1)
        matched = {fqn: info for fqn, info in registry.items() if f"app::{ns}::" in fqn}
        if matched:
            return _format_lines(matched)
        logger.debug("No tools found for namespace %s — falling back to full list", ns)

    # Context 2: native function prefix (llm_, native::, enrich_, store_)
    if re.search(
        r"\b(llm_|native::|enrich_|store_|alert_|table_|document_)\w*$", last_line
    ):
        native = {
            fqn: info for fqn, info in registry.items() if fqn.startswith("native::")
        }
        if native:
            return _format_lines(native)

    # Context 3: general — all native + capped app tools
    native = {fqn: info for fqn, info in registry.items() if fqn.startswith("native::")}
    app_tools = {fqn: info for fqn, info in registry.items() if fqn.startswith("app::")}
    # Sort app tools so result is deterministic
    capped_app = dict(sorted(app_tools.items())[:DEFAULT_APP_TOOL_CAP])
    combined = {**native, **capped_app}
    return _format_lines(combined)


def _format_lines(registry: dict[str, Any]) -> list[str]:
    """Format tool registry entries as compact summary lines.

    Native tools show both their short callable name and full FQN so the LLM
    knows to use e.g. `enrich_alert(` not `native::alert::enrich_alert(`.
    """
    lines = []
    for fqn, info in sorted(registry.items()):
        desc = info.get("description", "")
        params = list(info.get("parameters", {}).keys())
        param_str = ", ".join(params) if params else ""
        parts = fqn.split("::")
        short_name = parts[-1] if parts else fqn
        # Native tools: show "short_name  [fqn]  — desc"
        if fqn.startswith("native::"):
            entry = f"  {short_name}({param_str})  [{fqn}]"
        else:
            entry = f"  {fqn}({param_str})"
        if desc:
            entry += f"  — {desc}"
        lines.append(entry)
    return lines


# ── golden example loading ────────────────────────────────────────────────────


async def _load_example_script(tenant_id: str, session: AsyncSession) -> str | None:
    now = time.monotonic()
    cached = _example_cache.get(tenant_id)
    if cached is not None and now - cached[1] < CACHE_TTL:
        return cached[0]

    script: str | None = None

    preferred_stmt = (
        select(Task)
        .join(Component)
        .where(
            Component.tenant_id == tenant_id,
            Component.kind == ComponentKind.TASK,
            Component.name.ilike(GOLDEN_TASK_NAME),
            Component.status == "enabled",
        )
        .limit(1)
    )
    result = await session.execute(preferred_stmt)
    preferred_task = result.scalar_one_or_none()

    if preferred_task and preferred_task.script:
        script = preferred_task.script
        logger.debug(
            "Using golden example '%s' for tenant %s", GOLDEN_TASK_NAME, tenant_id
        )
    else:
        if preferred_task is None:
            logger.warning(
                "Golden example task '%s' not found for tenant %s — falling back to oldest "
                "task with >%d lines",
                GOLDEN_TASK_NAME,
                tenant_id,
                GOLDEN_FALLBACK_MIN_LINES,
            )
        else:
            logger.warning(
                "Golden example task '%s' has no script for tenant %s — falling back",
                GOLDEN_TASK_NAME,
                tenant_id,
            )

        fallback_stmt = (
            select(Task)
            .join(Component)
            .where(
                Component.tenant_id == tenant_id,
                Component.kind == ComponentKind.TASK,
                Component.status == "enabled",
                Task.script.isnot(None),
            )
            .order_by(Task.created_at.asc())
        )
        fb_result = await session.execute(fallback_stmt)
        for candidate in fb_result.scalars():
            candidate_script = candidate.script or ""
            if len(candidate_script.splitlines()) >= GOLDEN_FALLBACK_MIN_LINES:
                script = candidate_script
                await session.refresh(candidate, ["component"])
                logger.debug(
                    "Using fallback example '%s' for tenant %s",
                    candidate.component.name,
                    tenant_id,
                )
                break

        if script is None:
            logger.warning(
                "No fallback example task with >=%d lines found for tenant %s",
                GOLDEN_FALLBACK_MIN_LINES,
                tenant_id,
            )

    _example_cache[tenant_id] = (script, now)
    return script


# ── prompt building ───────────────────────────────────────────────────────────


def _build_prompts(
    script_prefix: str,
    script_suffix: str | None,
    trigger_kind: str,
    trigger_character: str | None,
    skill_content: str,
    tool_lines: list[str],
    example_script: str | None,
) -> tuple[str, str]:
    # Trim skill for character triggers to reduce prompt size
    skill_char_limit = SKILL_CHARS_BY_TRIGGER.get(trigger_kind)
    if skill_char_limit is not None and len(skill_content) > skill_char_limit:
        skill_snippet = (
            skill_content[:skill_char_limit] + "\n[...reference truncated for speed...]"
        )
    else:
        skill_snippet = skill_content

    tools_section = ""
    if tool_lines:
        tools_section = _TOOLS_SECTION_TEMPLATE.format(tool_lines="\n".join(tool_lines))

    # Skip example for character triggers — saves ~2 KB per request
    example_section = ""
    if example_script and trigger_kind != "character":
        example_section = _EXAMPLE_SECTION_TEMPLATE.format(
            example_script=example_script
        )

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        skill_content=skill_snippet,
        tools_section=tools_section,
        example_section=example_section,
    )

    suffix_section = ""
    if script_suffix:
        suffix_section = f"\nScript after cursor:\n```cy\n{script_suffix}\n```\n"

    trigger_char_section = ""
    if trigger_character:
        trigger_char_section = f', character: "{trigger_character}"'

    # Derive the partial identifier the user is currently typing so the LLM
    # doesn't treat the trigger character as a standalone token.
    partial_word_hint = ""
    if trigger_character and trigger_kind == "character":
        # Find the identifier fragment at the end of the prefix and append
        # the trigger character to get the full partial word.
        last_word_match = re.search(r"[\w:]+$", script_prefix)
        fragment = (
            last_word_match.group() if last_word_match else ""
        ) + trigger_character
        if fragment and fragment not in {".", "(", ")", "{", "}", "[", "]", " ", "\t"}:
            partial_word_hint = f'Partial identifier at cursor: "{fragment}"\n'

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        script_prefix=script_prefix,
        suffix_section=suffix_section,
        trigger_kind=trigger_kind,
        trigger_char_section=trigger_char_section,
        partial_word_hint=partial_word_hint,
    )
    return system_prompt, user_prompt


# ── JSON parsing ──────────────────────────────────────────────────────────────


def _parse_completions(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse completions JSON: %r", raw[:200])
        return []

    if not isinstance(data, list):
        logger.warning("Expected JSON array, got %s", type(data).__name__)
        return []

    valid_kinds = {"function", "keyword", "variable", "field", "snippet"}
    completions = []
    for item in data:
        if not isinstance(item, dict):
            continue
        insert_text = str(item.get("insert_text", ""))
        label = str(item.get("label", insert_text))
        detail = str(item.get("detail", ""))
        kind = item.get("kind", "snippet")
        if kind not in valid_kinds:
            kind = "snippet"
        completions.append(
            {
                "insert_text": insert_text,
                "label": label,
                "detail": detail,
                "kind": kind,
            }
        )
    return completions


def _validate_completions(
    completions: list[dict[str, Any]],
    registry: dict[str, Any],
    script_prefix: str,
) -> list[dict[str, Any]]:
    """Drop completions that reference invented tool names.

    Checks completions whose label looks like a tool short-name (no spaces,
    contains `_`). If the label resolves to a registered FQN short-name that
    does NOT exist in the registry, the completion is removed.

    This catches cases like `enrich_report` when only `enrich_alert` is real.
    Syntax completions (if, for, return…) and field completions are left alone.
    """
    # Build a set of valid short names from the registry
    # e.g. "native::alert::enrich_alert" → "enrich_alert"
    #      "app::virustotal::ip_reputation" → "ip_reputation"
    valid_short_names: set[str] = set()
    for fqn in registry:
        parts = fqn.split("::")
        if parts:
            valid_short_names.add(parts[-1])

    # Also add full FQNs themselves
    valid_fqns = set(registry.keys())

    CY_KEYWORDS = {"if", "else", "for", "return", "in", "true", "false", "null"}

    validated = []
    for c in completions:
        label = c["label"].strip().rstrip("(")
        # Only validate names that look like function/tool identifiers
        is_identifier = bool(re.match(r"^[\w:]+$", label)) and "_" in label
        if not is_identifier or label in CY_KEYWORDS:
            validated.append(c)
            continue

        # If it looks like a full FQN (contains ::) check directly
        if "::" in label:
            if label in valid_fqns:
                validated.append(c)
            else:
                logger.debug("Filtered hallucinated FQN: %s", label)
            continue

        # Short name — allow if it matches any registry entry's last segment
        if label in valid_short_names:
            validated.append(c)
        else:
            logger.debug("Filtered potentially hallucinated tool: %s", label)

    if len(validated) < len(completions):
        logger.info(
            "Filtered %d hallucinated completions (kept %d)",
            len(completions) - len(validated),
            len(validated),
        )
    return validated


# ── public API ────────────────────────────────────────────────────────────────


async def get_cy_completions(
    tenant_id: str,
    session: AsyncSession,
    script_prefix: str,
    script_suffix: str | None,
    trigger_kind: str,
    trigger_character: str | None,
) -> list[dict[str, Any]]:
    """Generate Cy script completions using LLM + skill + tool registry + example."""
    # Fast-path: return hardcoded Cy syntax snippets for known keywords — no LLM needed
    keyword_completions = _get_keyword_completions(
        script_prefix, trigger_kind, trigger_character
    )
    if keyword_completions is not None:
        logger.debug("Returning keyword snippets for fast-path (no LLM call)")
        return keyword_completions

    # Suppress completions when the cursor is inside an open string literal.
    # Without this guard the LLM injects code templates as string content.
    if _cursor_inside_string(script_prefix):
        logger.debug("Cursor inside string literal — suppressing completions")
        return []

    skill_content = await _load_skill_content(tenant_id)
    if not skill_content:
        logger.info(
            "cy-language-programming skill unavailable for tenant %s", tenant_id
        )
        return []

    registry = await _load_registry(tenant_id, session)
    tool_lines = _filter_tools_for_context(registry, script_prefix)

    # Example only loaded for non-character triggers
    example_script: str | None = None
    if trigger_kind != "character":
        example_script = await _load_example_script(tenant_id, session)

    system_prompt, user_prompt = _build_prompts(
        script_prefix=script_prefix,
        script_suffix=script_suffix,
        trigger_kind=trigger_kind,
        trigger_character=trigger_character,
        skill_content=skill_content,
        tool_lines=tool_lines,
        example_script=example_script,
    )

    integration_repo = IntegrationRepository(session)
    factory = LangChainFactory(
        IntegrationService(integration_repo=integration_repo),
        VaultClient(),
    )
    llm = await factory.get_primary_llm(tenant_id, session)

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    response = await llm.ainvoke(messages)
    raw = response.content if hasattr(response, "content") else str(response)

    completions = _parse_completions(str(raw))
    return _validate_completions(completions, registry, script_prefix)
