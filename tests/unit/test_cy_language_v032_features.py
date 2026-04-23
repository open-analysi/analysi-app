"""
Unit tests verifying cy-language v0.28-v0.32 features.

These tests confirm we are running the correct version and that
breaking changes + new features behave as expected in our environment.

Note: cy-language v0.38+ changed run()/run_async() to return JSON strings.
Use run_native()/run_native_async() for raw Python values.
"""

import json

from cy_language import Cy, analyze_script


# ---------------------------------------------------------------------------
# v0.28 – Breaking: `or`/`and` return values, not booleans
# ---------------------------------------------------------------------------
class TestOrAndReturnValues:
    """v0.28 changed or/and to return actual values instead of True/False."""

    def test_or_returns_first_truthy_value(self):
        cy = Cy()
        result = cy.run_native('return "hello" or "default"')
        assert result == "hello"

    def test_or_returns_right_when_left_falsy(self):
        cy = Cy()
        result = cy.run_native('return null or "fallback"')
        assert result == "fallback"

    def test_or_returns_right_for_zero(self):
        cy = Cy()
        assert cy.run_native("return 0 or 42") == 42

    def test_and_returns_last_truthy(self):
        cy = Cy()
        result = cy.run_native('return "a" and "b"')
        assert result == "b"

    def test_and_short_circuits_on_falsy(self):
        cy = Cy()
        assert cy.run_native('return null and "never"') is None


# ---------------------------------------------------------------------------
# v0.28 – Breaking: missing dict keys return null instead of throwing
# ---------------------------------------------------------------------------
class TestMissingKeysReturnNull:
    """v0.28 changed missing dict key access from error to null."""

    def test_missing_field_returns_null(self):
        cy = Cy()
        result = cy.run_native('data = {"a": 1}\nreturn data.missing')
        assert result is None

    def test_missing_bracket_key_returns_null(self):
        cy = Cy()
        result = cy.run_native('data = {"a": 1}\nreturn data["missing"]')
        assert result is None

    def test_chained_missing_returns_null(self):
        cy = Cy()
        result = cy.run_native('data = {"a": {}}\nreturn data.a.b.c.d')
        assert result is None

    def test_missing_key_with_fallback(self):
        """Idiomatic pattern: use `or` for defaults on missing keys."""
        cy = Cy()
        result = cy.run_native('data = {"name": "Alice"}\nreturn data.age or 25')
        assert result == 25


# ---------------------------------------------------------------------------
# v0.28 – New: |json filter in string interpolation
# ---------------------------------------------------------------------------
class TestJsonFilter:
    """v0.28 added |json for JSON serialization in interpolation."""

    def test_json_filter_dict(self):
        cy = Cy()
        # run() returns JSON string; the script returns a JSON-encoded string,
        # so the outer JSON wraps it. Use run_native to get the inner string,
        # then parse the JSON content.
        result = cy.run_native(
            'data = {"name": "Alice", "age": 30}\nreturn "${data|json}"'
        )
        assert json.loads(result) == {"name": "Alice", "age": 30}

    def test_json_filter_list(self):
        cy = Cy()
        result = cy.run_native('items = [1, 2, 3]\nreturn "${items|json}"')
        assert json.loads(result) == [1, 2, 3]


# ---------------------------------------------------------------------------
# v0.28 – New: dict iteration in for-in loops
# ---------------------------------------------------------------------------
class TestDictIteration:
    """v0.28 added dictionary iteration in for-in loops."""

    def test_iterate_dict_keys(self):
        cy = Cy()
        result = cy.run_native(
            'config = {"host": "localhost", "port": 8080}\n'
            "collected = []\n"
            "for (key in config) {\n"
            "    collected = collected + [key]\n"
            "}\n"
            "return collected"
        )
        assert set(result) == {"host", "port"}


# ---------------------------------------------------------------------------
# v0.30 – New native functions (35 added, now 45 total)
# ---------------------------------------------------------------------------
class TestNativeFunctions:
    """v0.30 expanded native functions from 10 to 45."""

    def test_split(self):
        cy = Cy()
        assert cy.run_native('return split("a,b,c", ",")') == ["a", "b", "c"]

    def test_replace(self):
        cy = Cy()
        assert (
            cy.run_native('return replace("hello world", "world", "cy")') == "hello cy"
        )

    def test_trim(self):
        cy = Cy()
        assert cy.run_native('return trim("  hello  ")') == "hello"

    def test_keys_and_values(self):
        cy = Cy()
        result = cy.run_native(
            'd = {"a": 1, "b": 2}\nk = keys(d)\nv = values(d)\n'
            'return {"keys": k, "values": v}'
        )
        assert set(result["keys"]) == {"a", "b"}
        assert set(result["values"]) == {1, 2}

    def test_reverse(self):
        cy = Cy()
        assert cy.run_native("return reverse([3, 1, 2])") == [2, 1, 3]

    def test_sort(self):
        cy = Cy()
        assert cy.run_native("return sort([3, 1, 2])") == [1, 2, 3]

    def test_abs_and_round(self):
        cy = Cy()
        assert cy.run_native("return abs(-5)") == 5
        assert cy.run_native("return round(3.14159, 2)") == 3.14

    def test_regex_match(self):
        cy = Cy()
        # regex_match(pattern, text) — pattern comes first
        assert cy.run_native('return regex_match("[0-9]+", "abc123")') is True
        assert cy.run_native('return regex_match("[A-Z]+", "hello")') is False

    def test_ip_checks(self):
        cy = Cy()
        assert cy.run_native('return is_ipv4("192.168.1.1")') is True
        assert cy.run_native('return is_ipv6("::1")') is True
        assert cy.run_native('return is_ip("not-an-ip")') is False

    def test_startswith_endswith(self):
        cy = Cy()
        assert cy.run_native('return startswith("alert_high", "alert")') is True
        assert cy.run_native('return endswith("report.pdf", ".pdf")') is True

    def test_num_and_bool_conversion(self):
        cy = Cy()
        # num() returns float for string input
        assert cy.run_native('return num("42")') == 42.0
        assert cy.run_native("return bool(0)") is False
        assert cy.run_native("return bool(1)") is True

    def test_now_returns_iso_string(self):
        cy = Cy()
        result = cy.run_native("return now()")
        assert isinstance(result, str)
        assert "T" in result  # ISO 8601 format


# ---------------------------------------------------------------------------
# v0.30 – New: field assignment with auto-create
# ---------------------------------------------------------------------------
class TestFieldAssignment:
    """v0.30 added field assignment that auto-creates intermediate dicts."""

    def test_simple_field_assignment(self):
        cy = Cy()
        result = cy.run_native('data = {"a": 1}\ndata.b = 2\nreturn data')
        assert result == {"a": 1, "b": 2}

    def test_nested_field_auto_create(self):
        cy = Cy()
        result = cy.run_native(
            "data = {}\ndata.a = {}\ndata.a.b = {}\ndata.a.b.c = 42\nreturn data"
        )
        assert result == {"a": {"b": {"c": 42}}}

    def test_compound_assignment(self):
        cy = Cy()
        result = cy.run_native(
            'counters = {"x": 10}\ncounters.x += 5\nreturn counters.x'
        )
        assert result == 15


# ---------------------------------------------------------------------------
# v0.32 – New: 2-part namespaced native functions
# ---------------------------------------------------------------------------
class TestNamespacedFunctions:
    """v0.32 added 2-part namespace aliases (str::, list::, json::, etc.)."""

    def test_str_namespace(self):
        cy = Cy()
        assert cy.run_native('return str::uppercase("hello")') == "HELLO"
        assert cy.run_native('return str::lowercase("WORLD")') == "world"
        assert cy.run_native('return str::trim("  hi  ")') == "hi"
        assert cy.run_native('return str::split("a,b", ",")') == ["a", "b"]

    def test_list_namespace(self):
        cy = Cy()
        assert cy.run_native("return list::sort([3, 1, 2])") == [1, 2, 3]
        assert cy.run_native("return list::reverse([1, 2, 3])") == [3, 2, 1]

    def test_json_namespace(self):
        cy = Cy()
        # json::stringify returns a string, so run_native gives us the raw string
        result = cy.run_native('return json::stringify({"a": 1})')
        assert json.loads(result) == {"a": 1}

    def test_math_namespace(self):
        cy = Cy()
        assert cy.run_native("return math::abs(-10)") == 10
        assert cy.run_native("return math::round(2.718, 1)") == 2.7

    def test_ip_namespace(self):
        cy = Cy()
        assert cy.run_native('return ip::is_v4("10.0.0.1")') is True
        assert cy.run_native('return ip::is_v6("::1")') is True
        assert cy.run_native('return ip::is_valid("garbage")') is False

    def test_type_namespace(self):
        cy = Cy()
        assert cy.run_native('return type::num("99")') == 99.0
        assert cy.run_native("return type::str(42)") == "42"
        assert cy.run_native("return type::bool(1)") is True

    def test_old_names_still_work(self):
        """Backward compatibility: un-namespaced names must still work."""
        cy = Cy()
        assert cy.run_native('return uppercase("hello")') == "HELLO"
        assert cy.run_native("return sort([3, 1, 2])") == [1, 2, 3]
        assert cy.run_native("return abs(-7)") == 7


# ---------------------------------------------------------------------------
# v0.32 – New: analyze_script() static analysis API
# ---------------------------------------------------------------------------
class TestAnalyzeScript:
    """v0.32 added analyze_script() for static extraction of tool calls."""

    def test_extracts_tool_calls(self):
        result = analyze_script(
            code="result = app::virustotal::ip_reputation(input.ip)\nreturn result",
            tool_registry={
                "app::virustotal::ip_reputation": {
                    "parameters": {"ip": {"type": "string"}},
                }
            },
        )
        assert "app::virustotal::ip_reputation" in result["tools_used"]

    def test_extracts_external_variables(self):
        result = analyze_script(
            code="x = input.value + 1\nreturn x",
            tool_registry={},
        )
        assert "input" in result["external_variables"]

    def test_no_tools_returns_empty(self):
        result = analyze_script(
            code="x = 1 + 2\nreturn x",
            tool_registry={},
        )
        assert result["tools_used"] == []
