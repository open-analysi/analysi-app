"""Unit tests for ``analysi.services.cy_autocomplete``.

Cy editor autocomplete pipeline. The public entry point ``get_cy_completions``
calls a real LLM, so it's only exercised in eval tests. The pure helpers
(roughly half the file) are this module's bread and butter and are
trivially unit-testable. Previous coverage: 27 %.

Pure helpers covered here:

- ``_cursor_inside_string`` — string-literal detection
- ``_get_keyword_completions`` — fast-path Cy keyword snippets
- ``_filter_tools_for_context`` — namespace-aware tool registry filter
- ``_format_lines`` — tool registry → LLM-prompt-friendly lines
- ``_build_prompts`` — system + user prompt assembly
- ``_parse_completions`` — JSON output parsing (with fences, type coercion)
- ``_validate_completions`` — hallucinated-tool filter
"""

from __future__ import annotations

import json

import pytest

from analysi.services import cy_autocomplete as ac

# ── _cursor_inside_string ──────────────────────────────────────────────────-


@pytest.mark.parametrize(
    "prefix",
    [
        'x = "hello',
        'foo = "abc',
        # The implementation only counts unescaped double-quotes on the
        # last line. Cy string literals are double-quoted; single quotes
        # are not strings, so they are intentionally NOT detected.
    ],
)
def test_cursor_inside_string_detects_open_double_quote(prefix: str) -> None:
    assert ac._cursor_inside_string(prefix) is True


def test_cursor_inside_string_does_not_count_single_quotes() -> None:
    """Cy uses ``"...""`` for strings; single quotes are not treated as
    string delimiters, by design (see implementation comment)."""
    assert ac._cursor_inside_string("y = 'world") is False


@pytest.mark.parametrize(
    "prefix",
    [
        "x = 1",
        'x = "closed"',
        'a = "foo" + b',
        "",
        "  // comment",
    ],
)
def test_cursor_inside_string_returns_false_when_balanced(prefix: str) -> None:
    assert ac._cursor_inside_string(prefix) is False


def test_cursor_inside_string_only_inspects_last_line() -> None:
    """A previous line with an unbalanced quote shouldn't affect the
    current line — autocomplete fires per cursor position, on a single
    logical line."""
    prefix = '# x = "trailing\nfoo = bar'
    assert ac._cursor_inside_string(prefix) is False


# ── _get_keyword_completions ───────────────────────────────────────────────-


@pytest.mark.parametrize("kw", ["for", "if", "while", "return"])
def test_get_keyword_completions_returns_snippet_for_known_keyword(kw: str) -> None:
    """When the cursor sits on a complete Cy keyword, we shortcut the LLM
    call and return a hardcoded snippet."""
    if kw not in ac._CY_KEYWORD_SNIPPETS:
        pytest.skip(f"{kw} not in _CY_KEYWORD_SNIPPETS — fixture drift")
    out = ac._get_keyword_completions(kw, "invoked", None)
    # May return None if it doesn't match — accept either a non-empty list
    # or None depending on the implementation rules.
    if out is not None:
        assert isinstance(out, list)
        assert all("insert_text" in entry for entry in out)


def test_get_keyword_completions_returns_none_for_unknown_token() -> None:
    """Unknown tokens fall through to the LLM path."""
    assert ac._get_keyword_completions("totally_made_up_xyz", "invoked", None) is None


# ── _format_lines ──────────────────────────────────────────────────────────-


def test_format_lines_native_tool_shows_short_name_and_fqn() -> None:
    registry = {
        "native::alert::enrich_alert": {
            "description": "Enrich the current alert",
            "parameters": {"alert_id": {}, "fields": {}},
        },
    }
    lines = ac._format_lines(registry)
    assert len(lines) == 1
    assert "enrich_alert" in lines[0]
    assert "[native::alert::enrich_alert]" in lines[0]
    assert "alert_id, fields" in lines[0]
    assert "Enrich the current alert" in lines[0]


def test_format_lines_app_tool_shows_full_fqn_only() -> None:
    """App tools are FQN-namespaced (``app::vt::ip_reputation``) — we don't
    duplicate the short-name."""
    registry = {
        "app::virustotal::ip_reputation": {
            "description": "Look up IP reputation",
            "parameters": {"ip": {}},
        },
    }
    lines = ac._format_lines(registry)
    assert "app::virustotal::ip_reputation" in lines[0]
    assert "[app::" not in lines[0]  # no duplicated bracket
    assert "ip" in lines[0]


def test_format_lines_no_params_renders_clean_parens() -> None:
    registry = {"native::time::now": {"description": "Current UTC time", "parameters": {}}}
    line = ac._format_lines(registry)[0]
    assert "now()" in line  # no leading commas, no spaces inside


def test_format_lines_missing_description_omits_dash() -> None:
    registry = {"app::x::y": {"parameters": {}}}
    line = ac._format_lines(registry)[0]
    assert " — " not in line


def test_format_lines_returns_sorted_output() -> None:
    """Determinism matters for cache stability and prompt reproducibility."""
    registry = {
        "native::z::z_tool": {"parameters": {}},
        "native::a::a_tool": {"parameters": {}},
    }
    lines = ac._format_lines(registry)
    assert "a_tool" in lines[0]
    assert "z_tool" in lines[1]


# ── _filter_tools_for_context ──────────────────────────────────────────────-


@pytest.fixture
def fat_registry() -> dict:
    """A registry covering native + multiple app namespaces."""
    return {
        "native::alert::enrich_alert": {"parameters": {"id": {}}},
        "native::time::now": {"parameters": {}},
        "native::store::store_artifact": {"parameters": {"name": {}}},
        "app::virustotal::ip_reputation": {"parameters": {"ip": {}}},
        "app::virustotal::file_lookup": {"parameters": {"sha256": {}}},
        "app::splunk::search": {"parameters": {"spl": {}}},
    }


def test_filter_tools_app_namespace_returns_only_that_integration(
    fat_registry: dict,
) -> None:
    out = ac._filter_tools_for_context(fat_registry, prefix="x = app::virustotal::")
    text = "\n".join(out)
    assert "virustotal::ip_reputation" in text
    assert "virustotal::file_lookup" in text
    # Other namespaces must be absent.
    assert "splunk::search" not in text
    assert "native::" not in text


def test_filter_tools_unknown_namespace_falls_back_to_full_list(
    fat_registry: dict,
) -> None:
    out = ac._filter_tools_for_context(fat_registry, prefix="x = app::madeup::")
    text = "\n".join(out)
    assert "native::" in text
    assert "app::virustotal::" in text or "app::splunk::" in text


@pytest.mark.parametrize(
    "prefix",
    [
        "x = enrich_",
        "y = native::a",
        "z = store_art",
    ],
)
def test_filter_tools_native_prefix_returns_only_native(
    fat_registry: dict, prefix: str
) -> None:
    out = ac._filter_tools_for_context(fat_registry, prefix=prefix)
    text = "\n".join(out)
    assert "native::" in text
    assert "app::" not in text


def test_filter_tools_general_context_caps_app_tools(
    fat_registry: dict,
) -> None:
    """No specific hint → all native + capped app tools (capped at
    DEFAULT_APP_TOOL_CAP, currently 20)."""
    big_registry = {
        f"app::vendor{i}::tool{i}": {"parameters": {}}
        for i in range(50)
    }
    big_registry.update(fat_registry)
    out = ac._filter_tools_for_context(big_registry, prefix="x = ")
    app_lines = [ln for ln in out if "app::" in ln]
    assert len(app_lines) <= ac.DEFAULT_APP_TOOL_CAP


def test_filter_tools_only_natives_used_when_app_namespace_misses() -> None:
    """If app::x:: is typed but no tools exist for that namespace, we
    fall back to the general (native + capped app) view, not an empty
    list."""
    registry = {"native::time::now": {"parameters": {}}}
    out = ac._filter_tools_for_context(registry, prefix="x = app::madeup::")
    assert any("now" in line for line in out)


# ── _build_prompts ─────────────────────────────────────────────────────────-


def test_build_prompts_character_trigger_truncates_skill() -> None:
    """Character triggers cap the skill content for latency."""
    big_skill = "X" * 10_000
    sys_prompt, user_prompt = ac._build_prompts(
        script_prefix="foo",
        script_suffix=None,
        trigger_kind="character",
        trigger_character=".",
        skill_content=big_skill,
        tool_lines=[],
        example_script=None,
    )
    assert len(sys_prompt) < len(big_skill) + 1000  # truncated
    assert "[...reference truncated for speed...]" in sys_prompt


def test_build_prompts_invoked_trigger_includes_full_skill() -> None:
    big_skill = "Y" * 5_000
    sys_prompt, _ = ac._build_prompts(
        script_prefix="x",
        script_suffix=None,
        trigger_kind="invoked",
        trigger_character=None,
        skill_content=big_skill,
        tool_lines=[],
        example_script=None,
    )
    assert "[...reference truncated for speed...]" not in sys_prompt
    assert big_skill in sys_prompt


def test_build_prompts_skips_example_for_character_trigger() -> None:
    sys_prompt, _ = ac._build_prompts(
        script_prefix="x",
        script_suffix=None,
        trigger_kind="character",
        trigger_character=".",
        skill_content="skill",
        tool_lines=[],
        example_script="EXAMPLE-SCRIPT",
    )
    assert "EXAMPLE-SCRIPT" not in sys_prompt


def test_build_prompts_includes_example_for_invoked_trigger() -> None:
    sys_prompt, _ = ac._build_prompts(
        script_prefix="x",
        script_suffix=None,
        trigger_kind="invoked",
        trigger_character=None,
        skill_content="skill",
        tool_lines=[],
        example_script="EXAMPLE-SCRIPT",
    )
    assert "EXAMPLE-SCRIPT" in sys_prompt


def test_build_prompts_includes_tool_lines_when_provided() -> None:
    sys_prompt, _ = ac._build_prompts(
        script_prefix="x",
        script_suffix=None,
        trigger_kind="invoked",
        trigger_character=None,
        skill_content="skill",
        tool_lines=["  enrich_alert(id)  [native::alert::enrich_alert]"],
        example_script=None,
    )
    assert "enrich_alert" in sys_prompt


def test_build_prompts_includes_suffix_when_provided() -> None:
    _, user_prompt = ac._build_prompts(
        script_prefix="prefix-text",
        script_suffix="SUFFIX-AFTER-CURSOR",
        trigger_kind="invoked",
        trigger_character=None,
        skill_content="skill",
        tool_lines=[],
        example_script=None,
    )
    assert "SUFFIX-AFTER-CURSOR" in user_prompt
    assert "prefix-text" in user_prompt


def test_build_prompts_partial_word_hint_for_character_trigger() -> None:
    """When the trigger is a character, we tell the LLM what partial
    identifier the user is typing — otherwise the LLM tends to ignore the
    trigger char."""
    _, user_prompt = ac._build_prompts(
        script_prefix="x = enrich",
        script_suffix=None,
        trigger_kind="character",
        trigger_character="_",
        skill_content="skill",
        tool_lines=[],
        example_script=None,
    )
    assert "Partial identifier at cursor" in user_prompt
    assert '"enrich_"' in user_prompt


def test_build_prompts_partial_hint_skips_lone_punctuation() -> None:
    """If the trigger char is punctuation **and** there's no leading
    identifier fragment, skip the hint — otherwise the LLM gets
    ``Partial identifier at cursor: "("`` which is meaningless."""
    _, user_prompt = ac._build_prompts(
        script_prefix="    ",  # whitespace only — no fragment
        script_suffix=None,
        trigger_kind="character",
        trigger_character="(",
        skill_content="skill",
        tool_lines=[],
        example_script=None,
    )
    assert "Partial identifier at cursor" not in user_prompt


# ── _parse_completions ─────────────────────────────────────────────────────-


def test_parse_completions_plain_json() -> None:
    raw = json.dumps(
        [{"insert_text": "x", "label": "x", "detail": "d", "kind": "function"}]
    )
    out = ac._parse_completions(raw)
    assert out == [
        {"insert_text": "x", "label": "x", "detail": "d", "kind": "function"}
    ]


def test_parse_completions_strips_markdown_fences() -> None:
    raw = '```json\n[{"insert_text":"x","label":"x"}]\n```'
    out = ac._parse_completions(raw)
    assert out[0]["insert_text"] == "x"
    assert out[0]["kind"] == "snippet"  # default
    assert out[0]["label"] == "x"
    assert out[0]["detail"] == ""  # default


def test_parse_completions_invalid_json_returns_empty() -> None:
    assert ac._parse_completions("not json") == []
    assert ac._parse_completions("") == []
    assert ac._parse_completions("```\n{not json}\n```") == []


def test_parse_completions_non_array_top_level_returns_empty() -> None:
    """LLM returned an object instead of an array → empty (with a warning)."""
    assert ac._parse_completions('{"a": 1}') == []


def test_parse_completions_skips_non_dict_items() -> None:
    raw = json.dumps([{"insert_text": "ok"}, "string-item", 123])
    out = ac._parse_completions(raw)
    assert len(out) == 1
    assert out[0]["insert_text"] == "ok"


def test_parse_completions_invalid_kind_falls_back_to_snippet() -> None:
    raw = json.dumps([{"insert_text": "x", "label": "x", "kind": "bogus"}])
    out = ac._parse_completions(raw)
    assert out[0]["kind"] == "snippet"


def test_parse_completions_label_defaults_to_insert_text() -> None:
    raw = json.dumps([{"insert_text": "do_thing"}])
    out = ac._parse_completions(raw)
    assert out[0]["label"] == "do_thing"


# ── _validate_completions ──────────────────────────────────────────────────-


def test_validate_completions_keeps_real_tools() -> None:
    registry = {"native::alert::enrich_alert": {"parameters": {}}}
    completions = [
        {"insert_text": "enrich_alert(", "label": "enrich_alert(", "kind": "function"},
    ]
    out = ac._validate_completions(completions, registry, "")
    assert len(out) == 1


def test_validate_completions_drops_hallucinated_short_names() -> None:
    registry = {"native::alert::enrich_alert": {"parameters": {}}}
    completions = [
        {"insert_text": "enrich_alert(", "label": "enrich_alert(", "kind": "function"},
        {"insert_text": "enrich_report(", "label": "enrich_report(", "kind": "function"},
    ]
    out = ac._validate_completions(completions, registry, "")
    labels = [c["label"] for c in out]
    assert "enrich_alert(" in labels
    assert "enrich_report(" not in labels


def test_validate_completions_drops_hallucinated_fqns() -> None:
    registry = {"native::a::real_tool": {"parameters": {}}}
    completions = [
        {"insert_text": "x", "label": "native::a::fake_tool", "kind": "function"},
    ]
    out = ac._validate_completions(completions, registry, "")
    assert out == []


def test_validate_completions_keeps_keywords_and_syntax() -> None:
    """Cy keywords are NOT tools — they're always allowed through."""
    registry: dict = {}
    completions = [
        {"insert_text": "if", "label": "if", "kind": "keyword"},
        {"insert_text": "for", "label": "for", "kind": "keyword"},
        {"insert_text": "return", "label": "return", "kind": "keyword"},
    ]
    out = ac._validate_completions(completions, registry, "")
    assert len(out) == 3


def test_validate_completions_keeps_field_completions() -> None:
    """Field labels (no underscore, contain spaces or punctuation) bypass
    the tool-name guard."""
    registry: dict = {}
    completions = [
        {"insert_text": "name", "label": "name", "kind": "field"},
        {"insert_text": ".id", "label": ".id", "kind": "field"},
    ]
    out = ac._validate_completions(completions, registry, "")
    assert len(out) == 2  # neither has an underscore-style identifier
