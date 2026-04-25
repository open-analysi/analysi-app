"""
Cy Native Time Functions - Local Extensions for Timestamp Conversion.

This module provides time-related native functions for Cy scripts,
extending cy-language's built-in time functions with format conversions
needed for security integrations (Splunk, log files, etc.).

Functions are registered via NATIVE_TOOL_METADATA in native_tools_registry.py
and available as native::time::format_timestamp in Cy scripts.
"""

from datetime import datetime, timedelta


def _parse_iso8601(timestamp: str) -> datetime:
    """Parse ISO 8601 timestamp to datetime.

    Handles various ISO 8601 formats including:
        - "2026-04-26T14:30:00Z" (UTC with Z suffix)
        - "2026-04-26T14:30:00+00:00" (UTC with offset)
        - "2026-04-26T14:30:00.123+00:00" (with milliseconds)
        - "2026-04-26T14:30:00-08:00" (timezone offset)

    Args:
        timestamp: ISO 8601 timestamp string

    Returns:
        Python datetime object

    Raises:
        ValueError: If timestamp format is invalid
    """
    # Handle Z suffix (convert to +00:00 format)
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(timestamp)
    except ValueError as e:
        raise ValueError(f"Invalid ISO 8601 timestamp: '{timestamp}': {e}")


def _format_iso8601(dt: datetime) -> str:
    """Format datetime to ISO 8601 string.

    Args:
        dt: Python datetime object

    Returns:
        ISO 8601 timestamp string
    """
    # Use isoformat() which preserves timezone
    iso_str = dt.isoformat()

    # If UTC and no timezone info, add Z suffix
    if dt.tzinfo is None or dt.utcoffset() == timedelta(0):
        if not iso_str.endswith("+00:00") and not iso_str.endswith("Z"):
            iso_str += "Z"
        elif iso_str.endswith("+00:00"):
            iso_str = iso_str[:-6] + "Z"

    return iso_str


class CyTimeFunctions:
    """Native Cy functions for timestamp conversion and formatting.

    These functions are registered via NATIVE_TOOL_METADATA and available
    in Cy scripts as native::tools::format_timestamp.
    """

    def format_timestamp(self, timestamp: str, target_format: str) -> str:
        """Convert ISO 8601 timestamp to various target formats.

        Takes an ISO 8601 timestamp and converts it to a target format.
        Commonly used for converting timestamps between systems like
        Splunk, log files, databases, etc.

        Args:
            timestamp: ISO 8601 timestamp string (e.g., "2026-04-26T03:30:42Z")
            target_format: Target format name. Supported formats:
                - "splunk": MM/DD/YYYY:HH:MM:SS (e.g., "01/01/2020:03:30:42")
                - "iso": ISO 8601 (normalized, e.g., "2026-04-26T03:30:42Z")
                - "date": YYYY-MM-DD (e.g., "2026-04-26")
                - "datetime": YYYY-MM-DD HH:MM:SS (e.g., "2026-04-26 03:30:42")
                - "clf": Common Log Format DD/Mon/YYYY:HH:MM:SS (e.g., "01/Jan/2020:03:30:42")

        Returns:
            Formatted timestamp string

        Raises:
            ValueError: If timestamp is invalid or format is not supported

        Examples:
            format_timestamp("2026-04-26T03:30:42Z", "splunk") -> "01/01/2020:03:30:42"
            format_timestamp("2026-04-26T03:30:42.222+00:00", "splunk") -> "01/01/2020:03:30:42"
            format_timestamp("2026-04-26T03:30:42Z", "date") -> "2026-04-26"
            format_timestamp("2026-04-26T03:30:42Z", "datetime") -> "2026-04-26 03:30:42"
            format_timestamp("2026-04-26T03:30:42Z", "clf") -> "01/Jan/2020:03:30:42"

        Common use case - Splunk SPL queries:
            # Build time range for SPL
            trigger_time = input.triggering_event_time
            earliest = native::tools::format_timestamp(subtract_duration(trigger_time, "15m"), "splunk")
            latest = native::tools::format_timestamp(add_duration(trigger_time, "15m"), "splunk")

            spl = \"\"\"
            search index=main earliest="${earliest}" latest="${latest}" ...
            \"\"\"
        """
        if not isinstance(timestamp, str):
            raise ValueError(
                f"format_timestamp() timestamp must be string, got {type(timestamp).__name__}"
            )
        if not isinstance(target_format, str):
            raise ValueError(
                f"format_timestamp() target_format must be string, got {type(target_format).__name__}"
            )

        # Normalize format name
        fmt = target_format.lower().strip()

        # Supported formats
        supported_formats = {"splunk", "iso", "date", "datetime", "clf"}
        if fmt not in supported_formats:
            raise ValueError(
                f"format_timestamp() unsupported format: '{target_format}'. "
                f"Supported formats: {', '.join(sorted(supported_formats))}"
            )

        # Parse the ISO 8601 timestamp
        try:
            dt = _parse_iso8601(timestamp)
        except ValueError as e:
            raise ValueError(f"format_timestamp() invalid timestamp: {e}")

        # Convert to target format
        if fmt == "splunk":
            # Splunk format: MM/DD/YYYY:HH:MM:SS
            return dt.strftime("%m/%d/%Y:%H:%M:%S")
        if fmt == "iso":
            # Return normalized ISO 8601
            return _format_iso8601(dt)
        if fmt == "date":
            # Simple date: YYYY-MM-DD
            return dt.strftime("%Y-%m-%d")
        if fmt == "datetime":
            # Simple datetime: YYYY-MM-DD HH:MM:SS
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        if fmt == "clf":
            # Common Log Format: DD/Mon/YYYY:HH:MM:SS
            return dt.strftime("%d/%b/%Y:%H:%M:%S")
        # Should never reach here due to validation above
        raise ValueError(f"Unsupported format: {target_format}")
