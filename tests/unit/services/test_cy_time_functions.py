"""Unit tests for ``analysi.services.cy_time_functions``.

``CyTimeFunctions.format_timestamp`` is a native Cy function that converts
ISO 8601 timestamps to a handful of target formats (Splunk, CLF, etc.).
Pure logic, no IO — perfect for parametrized happy-path + every-format +
every-rejection-path coverage. Previous coverage was 12.2 %.
"""

from __future__ import annotations

import pytest

from analysi.services.cy_time_functions import (
    CyTimeFunctions,
    _format_iso8601,
    _parse_iso8601,
)


@pytest.fixture
def cy_time() -> CyTimeFunctions:
    return CyTimeFunctions()


# ── _parse_iso8601 (private but worth covering directly) ────────────────────


@pytest.mark.parametrize(
    ("inp", "expected_iso"),
    [
        ("2026-04-26T14:30:00Z", "2026-04-26T14:30:00+00:00"),
        ("2026-04-26T14:30:00+00:00", "2026-04-26T14:30:00+00:00"),
        ("2026-04-26T14:30:00.123+00:00", "2026-04-26T14:30:00.123000+00:00"),
        ("2026-04-26T14:30:00-08:00", "2026-04-26T14:30:00-08:00"),
    ],
)
def test_parse_iso8601_supported_shapes(inp: str, expected_iso: str) -> None:
    dt = _parse_iso8601(inp)
    # Round-trip via isoformat — preserves tz.
    assert dt.isoformat() == expected_iso
    assert dt.tzinfo is not None  # project rule: tz-aware datetimes


def test_parse_iso8601_strips_z_suffix() -> None:
    dt = _parse_iso8601("2026-04-26T00:00:00Z")
    assert dt.utcoffset() is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_iso8601_invalid_raises_with_context() -> None:
    with pytest.raises(ValueError, match="Invalid ISO 8601 timestamp"):
        _parse_iso8601("not-a-timestamp")


# ── _format_iso8601 (private) ───────────────────────────────────────────────


def test_format_iso8601_utc_uses_z_suffix() -> None:
    """UTC datetimes are formatted with the canonical ``Z`` suffix."""
    dt = _parse_iso8601("2026-04-26T14:30:00+00:00")
    out = _format_iso8601(dt)
    assert out.endswith("Z")
    assert "+00:00" not in out


def test_format_iso8601_naive_gets_z_suffix() -> None:
    """Naive datetime is treated as UTC — Z is appended."""
    from datetime import datetime

    dt = datetime(2026, 4, 26, 14, 30, 0)  # noqa: DTZ001 — intentional naive
    out = _format_iso8601(dt)
    assert out.endswith("Z")


def test_format_iso8601_other_tz_keeps_offset() -> None:
    dt = _parse_iso8601("2026-04-26T14:30:00-08:00")
    out = _format_iso8601(dt)
    assert out.endswith("-08:00")


# ── format_timestamp — happy paths per format ───────────────────────────────


@pytest.mark.parametrize(
    ("inp", "fmt", "expected"),
    [
        ("2026-04-26T03:30:42Z", "splunk", "04/26/2026:03:30:42"),
        ("2026-04-26T03:30:42.222+00:00", "splunk", "04/26/2026:03:30:42"),
        ("2026-04-26T03:30:42Z", "iso", "2026-04-26T03:30:42Z"),
        ("2026-04-26T03:30:42Z", "date", "2026-04-26"),
        ("2026-04-26T03:30:42Z", "datetime", "2026-04-26 03:30:42"),
        ("2026-04-26T03:30:42Z", "clf", "26/Apr/2026:03:30:42"),
    ],
)
def test_format_timestamp_supported_formats(
    cy_time: CyTimeFunctions, inp: str, fmt: str, expected: str
) -> None:
    assert cy_time.format_timestamp(inp, fmt) == expected


def test_format_timestamp_iso_normalizes_offset(cy_time: CyTimeFunctions) -> None:
    """ISO output normalizes ``+00:00`` to ``Z``."""
    out = cy_time.format_timestamp("2026-04-26T03:30:42+00:00", "iso")
    assert out == "2026-04-26T03:30:42Z"


def test_format_timestamp_format_is_case_insensitive(cy_time: CyTimeFunctions) -> None:
    assert (
        cy_time.format_timestamp("2026-04-26T03:30:42Z", "SPLUNK")
        == "04/26/2026:03:30:42"
    )


def test_format_timestamp_format_is_whitespace_tolerant(
    cy_time: CyTimeFunctions,
) -> None:
    assert (
        cy_time.format_timestamp("2026-04-26T03:30:42Z", "  date  ")
        == "2026-04-26"
    )


def test_format_timestamp_preserves_non_utc_offset(cy_time: CyTimeFunctions) -> None:
    """Non-UTC offsets translate the wall-clock fields naturally — we don't
    convert to UTC behind the user's back."""
    out = cy_time.format_timestamp("2026-04-26T14:30:00-08:00", "datetime")
    assert out == "2026-04-26 14:30:00"


# ── format_timestamp — error paths ──────────────────────────────────────────


def test_format_timestamp_rejects_non_string_timestamp(
    cy_time: CyTimeFunctions,
) -> None:
    with pytest.raises(ValueError, match="timestamp must be string"):
        cy_time.format_timestamp(12345, "splunk")  # type: ignore[arg-type]


def test_format_timestamp_rejects_non_string_target_format(
    cy_time: CyTimeFunctions,
) -> None:
    with pytest.raises(ValueError, match="target_format must be string"):
        cy_time.format_timestamp(
            "2026-04-26T03:30:42Z",
            42,  # type: ignore[arg-type]
        )


def test_format_timestamp_rejects_unknown_format(cy_time: CyTimeFunctions) -> None:
    with pytest.raises(ValueError, match="unsupported format"):
        cy_time.format_timestamp("2026-04-26T03:30:42Z", "rfc2822")


def test_format_timestamp_unknown_format_lists_supported(
    cy_time: CyTimeFunctions,
) -> None:
    """Error message is actionable — lists every supported format."""
    with pytest.raises(ValueError, match=r"clf, date, datetime, iso, splunk"):
        cy_time.format_timestamp("2026-04-26T03:30:42Z", "rfc2822")


def test_format_timestamp_rejects_invalid_iso_timestamp(
    cy_time: CyTimeFunctions,
) -> None:
    with pytest.raises(ValueError, match="invalid timestamp"):
        cy_time.format_timestamp("yesterday", "splunk")


def test_format_timestamp_rejects_empty_timestamp(cy_time: CyTimeFunctions) -> None:
    with pytest.raises(ValueError, match="invalid timestamp"):
        cy_time.format_timestamp("", "splunk")
