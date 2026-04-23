"""Schedule interval parsing and next_run_at computation.

Provides parse_schedule_interval() and compute_next_run_at() for
pre-computed scheduling.
"""

import re
from datetime import UTC, datetime, timedelta


def parse_schedule_interval(schedule_value: str) -> int | None:
    """Parse schedule value to seconds.

    Examples:
        "60s" -> 60
        "5m" -> 300
        "1h" -> 3600
        "every 30s" -> 30

    Args:
        schedule_value: Schedule string

    Returns:
        Interval in seconds or None if cannot parse
    """
    if not schedule_value:
        return None

    # Remove "every" prefix if present
    value = schedule_value.lower().replace("every", "").strip()

    # Parse different formats
    patterns = [
        (r"^(\d+)s$", 1),  # seconds
        (r"^(\d+)m$", 60),  # minutes
        (r"^(\d+)h$", 3600),  # hours
        (r"^(\d+)d$", 86400),  # days
    ]

    for pattern, multiplier in patterns:
        match = re.match(pattern, value)
        if match:
            return int(match.group(1)) * multiplier

    # Try to parse as raw integer (assume seconds)
    try:
        return int(value)
    except ValueError:
        return None


def compute_next_run_at(
    schedule_type: str,
    schedule_value: str,
    from_time: datetime | None = None,
) -> datetime | None:
    """Compute the next run time for a schedule.

    Args:
        schedule_type: Schedule type (only "every" supported in v1).
        schedule_value: Interval string (e.g. "60s", "5m", "1h").
        from_time: Base time to compute from. Defaults to now(UTC).

    Returns:
        Next run datetime, or None if the interval cannot be parsed.
    """
    if schedule_type != "every":
        return None

    interval_seconds = parse_schedule_interval(schedule_value)
    if interval_seconds is None:
        return None

    base = from_time if from_time is not None else datetime.now(UTC)
    return base + timedelta(seconds=interval_seconds)
