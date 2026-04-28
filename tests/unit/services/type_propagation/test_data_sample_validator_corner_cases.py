"""Corner-case unit tests for ``data_sample_validator``.

The existing suite (``test_data_sample_validator.py``) covers
``_remove_required_fields`` and ``generate_schema_from_samples``. This file
fills the remaining gaps:

- ``validate_sample_against_schema``
- ``validate_data_samples_completeness``
- ``is_overly_generic_schema``
- ``validate_task_data_samples`` (top-level orchestrator)
- ``_remove_required_fields`` non-dict and list-with-non-dict branches

Pure-function coverage — no DB, no IO. Previous coverage on this file was
45 %.
"""

from __future__ import annotations

import pytest

from analysi.services.type_propagation.data_sample_validator import (
    _remove_required_fields,
    is_overly_generic_schema,
    validate_data_samples_completeness,
    validate_sample_against_schema,
    validate_task_data_samples,
)


# ── _remove_required_fields edge branches ──────────────────────────────────-


def test_remove_required_fields_passthrough_non_dict() -> None:
    assert _remove_required_fields("scalar-string") == "scalar-string"  # type: ignore[arg-type]
    assert _remove_required_fields(42) == 42  # type: ignore[arg-type]
    assert _remove_required_fields(None) is None  # type: ignore[arg-type]


def test_remove_required_fields_handles_list_of_mixed_items() -> None:
    """List containing dicts and non-dicts: dicts get cleaned, non-dicts pass through."""
    schema = {
        "anyOf": [
            {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}}},
            "literal-string",
            42,
        ],
    }
    out = _remove_required_fields(schema)
    assert "required" not in out["anyOf"][0]
    assert out["anyOf"][1] == "literal-string"
    assert out["anyOf"][2] == 42


# ── validate_sample_against_schema ─────────────────────────────────────────-


def test_validate_sample_against_schema_happy() -> None:
    valid, err = validate_sample_against_schema(
        {"ip": "1.2.3.4"},
        {"type": "object", "properties": {"ip": {"type": "string"}}},
    )
    assert valid is True
    assert err is None


def test_validate_sample_against_schema_returns_message_on_mismatch() -> None:
    valid, err = validate_sample_against_schema(
        {"ip": 1234},
        {
            "type": "object",
            "properties": {"ip": {"type": "string"}},
            "required": ["ip"],
        },
    )
    assert valid is False
    assert err is not None
    assert "string" in err  # jsonschema message includes the expected type


def test_validate_sample_against_schema_missing_required() -> None:
    valid, err = validate_sample_against_schema(
        {},
        {
            "type": "object",
            "properties": {"ip": {"type": "string"}},
            "required": ["ip"],
        },
    )
    assert valid is False
    assert err is not None


# ── validate_data_samples_completeness ──────────────────────────────────────


def test_completeness_all_present() -> None:
    valid, missing = validate_data_samples_completeness(
        [{"a": 1, "b": 2, "c": 3}], {"a", "b"}
    )
    assert valid is True
    assert missing == []


def test_completeness_missing_fields() -> None:
    valid, missing = validate_data_samples_completeness(
        [{"a": 1}], {"a", "b", "c"}
    )
    assert valid is False
    assert sorted(missing) == ["b", "c"]


def test_completeness_empty_samples_returns_all_required_missing() -> None:
    valid, missing = validate_data_samples_completeness([], {"a", "b"})
    assert valid is False
    assert sorted(missing) == ["a", "b"]


def test_completeness_empty_required() -> None:
    """Empty required set is trivially satisfied."""
    valid, missing = validate_data_samples_completeness([{"x": 1}], set())
    assert valid is True
    assert missing == []


# ── is_overly_generic_schema ───────────────────────────────────────────────-


def test_overly_generic_bare_object() -> None:
    assert is_overly_generic_schema({"type": "object"}) is True


def test_overly_generic_with_empty_properties() -> None:
    assert is_overly_generic_schema({"type": "object", "properties": {}}) is True


def test_not_overly_generic_with_real_properties() -> None:
    assert (
        is_overly_generic_schema(
            {"type": "object", "properties": {"ip": {"type": "string"}}}
        )
        is False
    )


def test_not_overly_generic_for_non_object_type() -> None:
    """Arrays, strings, etc. are not "overly generic" objects — they're
    just not objects at all."""
    assert is_overly_generic_schema({"type": "array"}) is False
    assert is_overly_generic_schema({"type": "string"}) is False


# ── validate_task_data_samples (orchestrator) ──────────────────────────────-


def test_task_data_samples_no_samples_rejected() -> None:
    valid, err = validate_task_data_samples(script="x = 1", data_samples=[])
    assert valid is False
    assert err is not None
    assert "data_samples" in err


def test_task_data_samples_overly_generic_rejected() -> None:
    """Single empty-dict sample → genson generates `{"type": "object"}` only,
    which is overly generic and gets rejected."""
    valid, err = validate_task_data_samples(script="x", data_samples=[{}])
    assert valid is False
    assert err is not None
    assert "too generic" in err


def test_task_data_samples_happy_no_expected_schema() -> None:
    valid, err = validate_task_data_samples(
        script="x = input['ip']",
        data_samples=[{"ip": "1.2.3.4", "context": "test"}],
    )
    assert valid is True
    assert err is None


def test_task_data_samples_required_fields_present() -> None:
    valid, err = validate_task_data_samples(
        script="x",
        data_samples=[{"ip": "1.2.3.4", "context": "abc"}],
        expected_schema={
            "type": "object",
            "properties": {"ip": {"type": "string"}},
            "required": ["ip"],
        },
    )
    assert valid is True
    assert err is None


def test_task_data_samples_missing_required_field_rejected() -> None:
    valid, err = validate_task_data_samples(
        script="x",
        data_samples=[{"context": "abc"}],
        expected_schema={
            "type": "object",
            "properties": {"ip": {"type": "string"}, "context": {"type": "string"}},
            "required": ["ip"],
        },
    )
    assert valid is False
    assert err is not None
    assert "ip" in err
    assert "missing required fields" in err


def test_task_data_samples_validates_each_sample() -> None:
    """Multiple samples — all must validate. Demonstrates loop coverage on
    line 249 of the source."""
    samples = [
        {"ip": "1.2.3.4", "context": "a"},
        {"ip": "5.6.7.8", "context": "b"},
    ]
    valid, err = validate_task_data_samples(script="x", data_samples=samples)
    assert valid is True
    assert err is None


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {}},  # no real props (overly generic)
    ],
)
def test_task_data_samples_helper_paths(schema: dict) -> None:
    """Sanity probe for the overly-generic guard with a hand-crafted schema."""
    assert is_overly_generic_schema(schema) is True
