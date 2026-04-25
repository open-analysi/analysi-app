"""Helper functions for IP address classification."""

import ipaddress
from typing import Any


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/internal.

    Private IP ranges:
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 192.168.0.0/16
    - 127.0.0.0/8 (loopback)
    - 169.254.0.0/16 (link-local)
    - fc00::/7 (IPv6 private)

    Args:
        ip_str: IP address string

    Returns:
        True if IP is private/internal
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except (ValueError, AttributeError):
        return False


def is_public_ip(ip_str: str) -> bool:
    """Check if an IP address is public/external.

    Args:
        ip_str: IP address string

    Returns:
        True if IP is public/external
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except (ValueError, AttributeError):
        return False


def classify_ip_context(event: dict[str, Any], field: str, ip_value: str) -> str:
    """Classify an IP based on context clues from the event.

    Args:
        event: The full event dictionary
        field: The field name containing the IP
        ip_value: The IP address value

    Returns:
        Classification: "internal", "external", or "unknown"
    """
    # Check if IP is private
    if is_private_ip(ip_value):
        return "internal"

    if is_public_ip(ip_value):
        return "external"

    # Use field naming conventions as hints
    internal_field_hints = ["src", "source", "client", "local", "internal"]
    external_field_hints = [
        "dest",
        "destination",
        "remote",
        "external",
        "threat",
        "attacker",
    ]

    field_lower = field.lower()

    for hint in internal_field_hints:
        if hint in field_lower:
            return "internal"

    for hint in external_field_hints:
        if hint in field_lower:
            return "external"

    return "unknown"


def is_threat_indicator(event: dict[str, Any], field: str, value: str) -> bool:
    """Determine if a value is likely a threat indicator (IOC).

    Args:
        event: The full event dictionary
        field: The field name containing the value
        value: The value to evaluate

    Returns:
        True if likely a threat indicator
    """
    field_lower = field.lower()

    # Fields that explicitly indicate threats
    threat_field_patterns = [
        "threat",
        "malicious",
        "attacker",
        "adversary",
        "hostile",
        "bad",
        "evil",
        "c2",
        "command_control",
        "suspicious",
    ]

    for pattern in threat_field_patterns:
        if pattern in field_lower:
            return True

    # Check if it's an external IP in dest/remote fields (potential threat)
    if (
        is_public_ip(value)
        and any(hint in field_lower for hint in ["dest", "remote", "target"])
        and not is_our_infrastructure(value, event)
    ):
        return True

    # Check for known malicious patterns
    return bool(is_malicious_pattern(value))


def is_our_infrastructure(value: str, event: dict[str, Any]) -> bool:
    """Check if a value belongs to our own infrastructure.

    This is a heuristic check - in production, this should check against
    an inventory of known good assets.

    Args:
        value: The value to check (IP, hostname, etc.)
        event: The full event for context

    Returns:
        True if likely our infrastructure
    """
    # Check for internal/private IPs
    if is_private_ip(value):
        return True

    # Check for known cloud provider patterns that might be ours
    our_domains = [
        ".local",
        ".internal",
        ".corp",
        ".lan",
        "localhost",
        "workstation",
        "server",
    ]

    value_lower = str(value).lower()
    for domain in our_domains:
        if domain in value_lower:
            return True

    # Check if marked as our asset in the event
    return bool(
        event.get("dest_risk_object_type") == "system" and value == event.get("dest")
    )


def is_malicious_pattern(value: str) -> bool:
    """Check if a value matches known malicious patterns.

    Args:
        value: The value to check

    Returns:
        True if matches malicious patterns
    """

    value_lower = str(value).lower()

    # Check for suspicious TLDs often used in attacks
    suspicious_tlds = [".tk", ".ml", ".ga", ".cf"]
    for tld in suspicious_tlds:
        if value_lower.endswith(tld):
            return True

    # Check for IP instead of domain in URLs (common in phishing)
    return bool(
        value_lower.startswith("http://") and any(c.isdigit() for c in value[7:10])
    )
