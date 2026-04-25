"""Glom mapping specifications for Splunk Notable events."""

import re
from typing import Any

from glom import Coalesce, Path

from .splunk_notable_lists import (
    INVALID_VALUES,
    extract_all_iocs,
    extract_all_risk_entities,
    is_valid_user,
)

# Entity type constants
_ENTITY_USER = "user"
_ENTITY_DEVICE = "device"


def clean_string_value(value: str | None) -> str | None:
    """Clean string values by removing trailing junk data.

    Some Splunk fields may contain trailing \nNONE_MAPPED or other artifacts.

    Args:
        value: String value to clean

    Returns:
        Cleaned string or None
    """
    if not value:
        return None

    # Convert to string and strip whitespace
    cleaned = str(value).strip()

    # Remove common trailing artifacts
    if "\nNONE_MAPPED" in cleaned:
        cleaned = cleaned.split("\nNONE_MAPPED")[0]

    return cleaned if cleaned else None


def get_primary_risk_entity(obj: dict) -> tuple[str | None, str | None]:  # noqa: C901
    """Extract the primary risk entity value and type with validation.

    Priority:
    1. normalized_risk_object (if valid)
    2. risk_object (if normalized is invalid/empty)
    3. user fields
    4. dest/src fields

    Returns:
        Tuple of (entity_value, entity_type) or (None, None) if no valid entity
    """
    # First check normalized_risk_object with validation
    if obj.get("normalized_risk_object"):
        cleaned = clean_string_value(obj.get("normalized_risk_object"))
        if cleaned and is_valid_entity_value(cleaned):
            risk_type = obj.get("risk_object_type", "system")
            # Map risk_object_type to our entity types
            if risk_type == "user":
                if is_valid_user(cleaned):
                    return cleaned, "user"
            elif risk_type in ["system", "device", "file_hash", "other"]:
                return cleaned, "device"
            else:
                return cleaned, "device"  # Default to device for unknown types

    # Fall back to risk_object if normalized is invalid
    if obj.get("risk_object"):
        cleaned = clean_string_value(obj.get("risk_object"))
        if cleaned and is_valid_entity_value(cleaned):
            risk_type = obj.get("risk_object_type", "system")
            if risk_type == "user":
                if is_valid_user(cleaned):
                    return cleaned, "user"
            else:
                return cleaned, "device"

    # Fall back to other fields
    candidates = [
        (obj.get("user"), "user"),
        (obj.get("src_user"), "user"),
        (obj.get("dest_user"), "user"),
        (obj.get("dest"), "system"),
        (obj.get("src"), "system"),
    ]

    for value, field_type in candidates:
        if value:
            cleaned = clean_string_value(value)
            if cleaned:
                if field_type == "user":
                    if is_valid_user(cleaned):
                        return cleaned, "user"
                else:
                    # For system fields, validate it's not a pathological value
                    if is_valid_entity_value(cleaned):
                        return cleaned, "device"

    return None, None


def is_valid_entity_value(value: str) -> bool:
    """Check if an entity value is valid (not a placeholder or invalid value).

    Args:
        value: Entity value to validate

    Returns:
        True if the value appears to be valid, False otherwise
    """
    if not value:
        return False

    cleaned = value.strip().lower()
    return cleaned not in INVALID_VALUES


# Glom specs for mapping between formats based on NotableSchema.txt
NOTABLE_TO_ALERTCREATE = {
    # Required fields - use Splunk Notable field names from schema
    "title": Coalesce(
        Path("rule_name"),
        Path("rule_title"),
        Path("search_name"),
        default="Unknown Alert",
    ),
    "triggering_event_time": Path("_time"),  # Notable has _time field
    "severity": Coalesce(Path("severity"), Path("urgency"), default="unknown"),
    # Source information from Notable
    "source_vendor": lambda x: "Splunk",
    "source_product": lambda x: "Enterprise Security",
    "source_category": lambda x: map_security_domain_to_category(
        x.get("security_domain")
    ),
    "rule_name": Coalesce(Path("rule_name"), Path("search_name"), default=None),
    "alert_type": Coalesce(Path("security_domain"), default=None),
    "device_action": lambda x: normalize_device_action(x.get("action")),
    # Source system reference - Splunk event_id
    "source_event_id": Coalesce(Path("event_id"), default=None),
    # Primary entities - Check risk_object fields first, then user/dest fields
    "primary_risk_entity_value": lambda obj: get_primary_risk_entity(obj)[0],
    "primary_risk_entity_type": lambda obj: get_primary_risk_entity(obj)[1],
    # IOC extraction - check threat_object/threat_entity first, then other fields
    "primary_ioc_value": Coalesce(
        Path("threat_object"),
        Path("threat_entity"),
        lambda x: extract_primary_ioc(x),
        default=None,
    ),
    "primary_ioc_type": lambda x: determine_ioc_type(x),
    # Structured context fields
    "network_info": lambda obj: extract_network_info(obj),
    "web_info": lambda obj: extract_web_info(obj),
    "process_info": lambda obj: extract_process_info(obj),
    "cve_info": lambda obj: extract_cve_info(obj),
    "other_activities": lambda obj: extract_other_activities(obj),
    # Lists of all entities and IOCs
    "risk_entities": lambda obj: extract_all_risk_entities(obj),
    "iocs": lambda obj: extract_all_iocs_with_primary(obj),
    # Detection time (firstTime/lastTime from Notable)
    "detected_at": Coalesce(Path("firstTime"), Path("_time"), default=None),
}


def safe_get(obj: dict[str, Any] | None, path: str, default: Any = None) -> Any:
    """Safely get nested values from a dictionary.

    This replaces the lambdas in ALERTCREATE_TO_NOTABLE with a safer approach
    that handles None objects and missing keys gracefully.

    Args:
        obj: Dictionary to get value from (can be None)
        path: Dot-separated path to the value (e.g., "network_info.src_ip")
        default: Default value if path not found or obj is None

    Returns:
        The value at path or default if not found

    Examples:
        >>> safe_get({"a": {"b": "c"}}, "a.b")
        'c'
        >>> safe_get(None, "a.b", "default")
        'default'
        >>> safe_get({"a": {}}, "a.b.c", "default")
        'default'
    """
    if obj is None:
        return default

    # Handle empty path - return the object itself
    if not path:
        return obj

    parts = path.split(".")
    current: Any = obj

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
            if current is None:
                return default
        else:
            return default

    return current if current is not None else default


# Keep the mapping for glom compatibility
ALERTCREATE_TO_NOTABLE = {
    # Core rule fields
    "rule_name": Coalesce(Path("rule_name"), Path("title"), default=""),
    "rule_title": Path("title"),
    "rule_description": Coalesce(Path("description"), Path("title"), default=""),
    "search_name": Coalesce(Path("rule_name"), Path("title"), default=""),
    # Time fields
    "_time": Path("triggering_event_time"),
    "firstTime": Coalesce(
        Path("detected_at"), Path("triggering_event_time"), default=None
    ),
    "lastTime": Path("triggering_event_time"),
    # Severity and priority fields
    "severity": Path("severity"),
    "urgency": Path("severity"),  # Map severity to urgency
    "priority": Path("severity"),
    "severities": Path("severity"),
    # Status fields (set defaults for new alerts)
    "status": lambda x: "1",  # 1 = New
    "status_label": lambda x: "New",
    "status_description": lambda x: "Finding is recent and not reviewed.",
    "status_default": lambda x: "true",
    "status_end": lambda x: "false",
    "status_group": lambda x: "New",
    # Owner fields
    "owner": lambda x: "unassigned",
    "owner_realname": lambda x: "unassigned",
    # Security domain
    "security_domain": lambda obj: map_category_to_security_domain(
        safe_get(obj, "source_category")
    ),
    # Host/System information
    # Pattern: src/dest should contain hostname (priority) or IP if no hostname
    #          src_ip/dest_ip should contain IP address only
    "dest": lambda obj: (
        safe_get(obj, "primary_risk_entity_value")
        if safe_get(obj, "primary_risk_entity_type")
        in ["host", "device", _ENTITY_DEVICE, "device"]
        else safe_get(obj, "network_info.dest_hostname")
        or safe_get(obj, "network_info.dest_ip")
        or safe_get(obj, "network_info.destination_ip")
    ),
    "dest_ip": lambda obj: (
        safe_get(obj, "network_info.dest_ip")
        or safe_get(obj, "network_info.destination_ip")
    ),
    "src": lambda obj: (
        # Prioritize hostname over IP for src field
        safe_get(obj, "network_info.src_hostname")
        or safe_get(obj, "network_info.src_ip")
        or safe_get(obj, "network_info.source_ip")
        or (
            safe_get(obj, "primary_ioc_value")
            if safe_get(obj, "primary_ioc_type") == "ip"
            else None
        )
    ),
    "src_ip": lambda obj: (
        safe_get(obj, "network_info.src_ip") or safe_get(obj, "network_info.source_ip")
    ),
    "host": lambda obj: (
        safe_get(obj, "primary_risk_entity_value")
        if safe_get(obj, "primary_risk_entity_type")
        in ["host", "device", _ENTITY_DEVICE, "device"]
        else safe_get(obj, "network_info.dest_hostname", "unknown")
    ),
    # User information
    "user": lambda obj: (
        safe_get(obj, "primary_risk_entity_value")
        if safe_get(obj, "primary_risk_entity_type") in ["user", _ENTITY_USER]
        else None
    ),
    "src_user": lambda obj: extract_user_from_risk_entities(obj, "src_user"),
    "dest_user": lambda obj: extract_user_from_risk_entities(obj, "dest_user"),
    # Process/IOC information (use standard ProcessInfo schema field names)
    "process": lambda obj: (
        safe_get(obj, "primary_ioc_value")
        if safe_get(obj, "primary_ioc_type") == "process"
        else safe_get(obj, "process_info.process_cmd")
    ),
    "process_name": lambda obj: extract_process_name_from_notable(obj),
    # Network fields from network_info (support both short and long field names)
    "src_port": lambda obj: (
        safe_get(obj, "network_info.src_port")
        or safe_get(obj, "network_info.source_port")
    ),
    "dest_port": lambda obj: (
        safe_get(obj, "network_info.dest_port")
        or safe_get(obj, "network_info.destination_port")
    ),
    "protocol": lambda obj: safe_get(obj, "network_info.protocol"),
    "bytes_in": lambda obj: safe_get(obj, "network_info.bytes_in"),
    "bytes_out": lambda obj: safe_get(obj, "network_info.bytes_out"),
    # Web fields from web_info (use standard WebInfo schema field names)
    "url": lambda obj: safe_get(obj, "web_info.url"),
    "requested_url": lambda obj: safe_get(obj, "web_info.url"),
    "http_method": lambda obj: safe_get(obj, "web_info.http_method"),
    "method": lambda obj: safe_get(obj, "web_info.http_method"),
    "user_agent": lambda obj: safe_get(obj, "web_info.user_agent"),
    "http_user_agent": lambda obj: safe_get(obj, "web_info.user_agent"),
    "http_referrer": lambda obj: safe_get(obj, "web_info.http_referrer"),
    "referrer": lambda obj: safe_get(obj, "web_info.http_referrer"),
    "http_status": lambda obj: safe_get(obj, "web_info.http_status"),
    "cookie": lambda obj: safe_get(obj, "web_info.cookie"),
    "http_content_type": lambda obj: safe_get(obj, "web_info.http_content_type"),
    # Risk scores (calculate from severity)
    "risk_score": lambda obj: calculate_risk_score(safe_get(obj, "severity")),
    "dest_risk_score": lambda obj: str(
        int(float(calculate_risk_score(safe_get(obj, "severity"))) * 0.66)
    ),
    "user_risk_score": lambda obj: str(
        int(float(calculate_risk_score(safe_get(obj, "severity"))) * 0.33)
    ),
    "dest_risk_object_type": lambda obj: "system",
    "user_risk_object_type": lambda obj: "user",
    # Event metadata
    "notable_type": lambda x: "notable",
    "eventtype": lambda x: ["notable", "modnotable_results"],
    "source": lambda obj: (
        f"{safe_get(obj, 'source_vendor', 'Unknown')} {safe_get(obj, 'source_product', '')}".strip()
    ),
    "sourcetype": lambda x: "stash",
    "index": lambda x: "notable",
    # Device action
    "action": Coalesce(Path("device_action"), default=""),
    # Risk object fields - reconstruct from risk entities
    "risk_object": lambda obj: extract_risk_object_from_nas(obj),
    "normalized_risk_object": lambda obj: extract_risk_object_from_nas(
        obj, normalized=True
    ),
    "risk_object_type": lambda obj: extract_risk_object_type_from_nas(obj),
    # Threat/IOC fields - populate from primary_ioc_value
    "threat_object": Coalesce(Path("primary_ioc_value"), default=None),
    "threat_entity": Coalesce(Path("primary_ioc_value"), default=None),
    "threat_object_type": lambda obj: (
        safe_get(obj, "primary_ioc_type")
        if safe_get(obj, "primary_ioc_value")
        else None
    ),
    # Alert type and category
    "alert_type": Coalesce(Path("alert_type"), default=""),
    "signature": Coalesce(Path("rule_name"), Path("alert_type"), default=""),
    # Additional source info
    "vendor_product": lambda obj: (
        f"{safe_get(obj, 'source_vendor', '')} {safe_get(obj, 'source_product', '')}".strip()
    ),
    # Additional notable fields from schema
    "count": lambda x: 2,  # Hardcoded as per schema
    "linecount": lambda x: "1",
    "orig_action_name": lambda x: "notable",
    "savedsearch_description": lambda obj: safe_get(obj, "title", ""),
    # Splunk internal fields
    "splunk_server": lambda x: "analysi-indexer",
    "tag": lambda x: ["modaction_result"],
    # _raw field in Splunk's key=value format (Common Information Model)
    "_raw": lambda obj: create_splunk_raw_field(obj) if obj else "",
}


def map_security_domain_to_category(domain: str | None) -> str | None:
    """Map Splunk security domain to SourceCategory enum.

    Args:
        domain: Security domain from Splunk

    Returns:
        SourceCategory enum value or None
    """
    if not domain:
        return None

    domain_lower = str(domain).lower()

    # Map Splunk domains to SourceCategory enum values (expanded)
    # Splunk security_domain values: access, endpoint, network, threat, identity, audit
    mapping = {
        "endpoint": "EDR",
        "network": "Firewall",
        "identity": "Identity",
        "access": "Identity",  # Access management maps to Identity
        "audit": "Identity",  # Audit events map to Identity
        "threat": "IDS/IPS",  # Threat detection/hunting from SIEM/XDR/SOAR maps to IDS/IPS
        # Additional mappings for other potential domains
        "cloud": "Cloud",
        "dlp": "DLP",
        "data": "DLP",
        "email": "Email",
        "web": "Web",
        "waf": "WAF",
        "database": "Database",
        "vulnerability": "Vulnerability",
        "ids": "IDS/IPS",
        "ips": "IDS/IPS",
        "ndr": "NDR",
        "casb": "CASB",
        "printer": "Printer",
    }

    return mapping.get(domain_lower)


def extract_primary_ioc(event: dict[str, Any]) -> str | None:
    """Extract primary IOC from event based on Notable schema.

    Priority:
    1. threat_object (explicit threat indicator)
    2. threat_entity (alternative threat field)
    3. Other IOC fields as fallback

    Args:
        event: Splunk notable event

    Returns:
        Primary IOC value or None
    """
    # Priority order for IOC extraction based on Notable schema
    # threat_object/threat_entity are explicit threat indicators and should be prioritized
    ioc_fields = [
        "threat_object",  # Splunk's primary threat indicator - HIGHEST PRIORITY
        "threat_entity",  # Alternative threat field name
        "requested_url",  # Web attack URLs (often contain the malicious payload)
        "process",  # Full command line from Notable
        "process_name",  # Just the process name
        "parent_process",  # Parent process path
        "file_hash",
        "url",
        "domain",
        "ip",
        "email",
        "original_file_name",
        "registry_path",
    ]

    for field in ioc_fields:
        if event.get(field):
            value = str(event[field]).strip()
            # Clean up the value
            if value and value not in ["", "-", "unknown", "n/a"]:
                return value

    return None


def determine_ioc_type(event: dict[str, Any]) -> str | None:  # noqa: C901
    """Determine IOC type from event.

    Args:
        event: Splunk notable event

    Returns:
        IOCType enum value or None
    """
    # Check for threat_object_type field first (explicit type)
    if event.get("threat_object_type"):
        threat_type = str(event["threat_object_type"]).lower()
        type_mapping = {
            "hash": "filehash",
            "file_hash": "filehash",
            "ip": "ip",
            "domain": "domain",
            "url": "url",
            "email": "email",
            "process": "process",
            "registry": "registry",
        }
        if threat_type in type_mapping:
            return type_mapping[threat_type]

    # Check for Splunk's threat fields and infer type
    if event.get("threat_object") or event.get("threat_entity"):
        # Try to infer type from the value itself
        threat_val = event.get("threat_object") or event.get("threat_entity")
        if isinstance(threat_val, str):
            # Simple heuristics for common IOC types (map to IOCType enum values)
            if threat_val.startswith("http://") or threat_val.startswith("https://"):
                return "url"
            if len(threat_val) in [32, 40, 64, 128]:  # Common hash lengths
                return "filehash"
            if (
                "." in threat_val
                and threat_val.count(".") == 3
                and all(
                    part.isdigit() and 0 <= int(part) <= 255
                    for part in threat_val.split(".")
                )
            ):  # Valid IP
                return "ip"
            if "." in threat_val:  # Likely domain
                return "domain"
            if "\\" in threat_val or "/" in threat_val:  # Path
                return "filename"
        return None  # Return None for unknown

    # Check for requested_url (web attacks)
    if event.get("requested_url"):
        return "url"

    # Map specific fields to IOCType enum values
    if event.get("process") or event.get("process_name"):
        return "process"
    if event.get("file_hash"):
        return "filehash"
    if event.get("url"):
        return "url"
    if event.get("domain"):
        return "domain"
    if event.get("ip"):
        return "ip"
    if event.get("original_file_name"):
        return "filename"

    return None


def determine_entity_type(event: dict[str, Any]) -> str:
    """Determine entity type from event.

    Args:
        event: Splunk notable event

    Returns:
        Entity type string
    """
    if "dest" in event or "dest_host" in event:
        return "host"
    if "user" in event or "src_user" in event:
        return "user"
    if "src" in event or "src_ip" in event:
        return "ip"
    return "unknown"


def extract_network_info(event: dict[str, Any]) -> dict[str, Any] | None:  # noqa: C901
    """Extract network information from event.

    Args:
        event: Splunk notable event

    Returns:
        Network information dictionary
    """
    import ipaddress

    network_info: dict[str, Any] = {}

    # Helper function to determine if a value is an IP address
    def is_ip_address(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except (ValueError, AttributeError):
            return False

    # Handle source - could be IP or hostname
    # Note: src field can contain URLs, hostnames, or IPs
    if event.get("src"):
        src_value = str(event["src"])
        # Skip URLs - they're not network endpoints
        if not src_value.startswith(("http://", "https://", "ftp://")):
            if is_ip_address(src_value):
                network_info["src_ip"] = src_value
                # If we only have IP in src, also populate src_hostname for consistency
                if "src_ip" not in event:
                    network_info["src_hostname"] = None  # Explicitly no hostname
            else:
                network_info["src_hostname"] = src_value

    # Also check for explicit src_ip field (takes precedence for IP)
    if event.get("src_ip"):
        network_info["src_ip"] = event["src_ip"]

    # Handle destination - could be IP or hostname
    # Based on data: dest usually contains hostname (93.3% of cases)
    if event.get("dest"):
        dest_value = str(event["dest"])
        # Skip URLs
        if not dest_value.startswith(("http://", "https://", "ftp://")):
            if is_ip_address(dest_value):
                network_info["dest_ip"] = dest_value
                # If we only have IP in dest, also note no hostname
                if "dest_ip" not in event:
                    network_info["dest_hostname"] = None
            else:
                network_info["dest_hostname"] = dest_value

    # Also check for explicit dest_ip field (takes precedence for IP)
    if event.get("dest_ip"):
        network_info["dest_ip"] = event["dest_ip"]

    # Check for explicit hostname fields (rare but possible)
    if event.get("src_host"):
        network_info["src_hostname"] = event["src_host"]
    if event.get("dest_host"):
        network_info["dest_hostname"] = event["dest_host"]

    # Port and protocol fields
    simple_fields = {
        "src_port": "src_port",
        "dest_port": "dest_port",
        "protocol": "protocol",
        "bytes_in": "bytes_in",
        "bytes_out": "bytes_out",
        "packets_in": "packets_in",
        "packets_out": "packets_out",
    }

    for event_field, info_field in simple_fields.items():
        if event.get(event_field):
            network_info[info_field] = event[event_field]

    # Infer dest_port from URL scheme if not explicitly set
    if "dest_port" not in network_info:
        url = event.get("requested_url") or event.get("url") or ""
        if url.startswith("https://"):
            network_info["dest_port"] = 443
        elif url.startswith("http://"):
            network_info["dest_port"] = 80

    # Only return if we found network-related data
    return network_info if network_info else None


def map_category_to_security_domain(category: str | None) -> str:
    """Map SourceCategory to Splunk security domain.

    Args:
        category: Source category value

    Returns:
        Splunk security domain
    """
    if not category:
        return "endpoint"

    category_lower = str(category).lower()

    mapping = {
        "edr": "endpoint",
        "firewall": "network",
        "identity": "identity",
        "cloud": "cloud",
        "dlp": "data",
        "siem": "audit",
        "waf": "network",
    }

    return mapping.get(category_lower, "endpoint")


def calculate_risk_score(severity: str | None) -> str:
    """Calculate risk score from severity.

    Args:
        severity: Alert severity

    Returns:
        Risk score as string
    """
    if not severity:
        return "50"

    severity_lower = str(severity).lower()

    scores = {
        "critical": "100",
        "high": "75",
        "medium": "50",
        "low": "25",
        "info": "10",
    }

    return scores.get(severity_lower, "50")


def extract_process_name_from_notable(obj: dict[str, Any] | None) -> str | None:
    """Extract process name from NAS object for Notable reconstruction.

    This extracts just the executable name from process info or IOC.
    Uses standard ProcessInfo schema field names.

    Args:
        obj: Alert object (NAS format)

    Returns:
        Process name (executable only) or None
    """
    import os

    if not obj:
        return None

    # First check process_info for the name field (standard schema)
    process_info = obj.get("process_info") or {}
    if process_info.get("name"):
        return process_info.get("name")

    # Otherwise extract from command line (cmd is standard schema field)
    process_cmd = None
    if process_info.get("cmd"):
        process_cmd = process_info.get("cmd")
    elif obj.get("primary_ioc_type") == "process" and obj.get("primary_ioc_value"):
        process_cmd = obj.get("primary_ioc_value")

    if process_cmd:
        # Extract just the executable name from full path/command
        # Handle quoted paths and arguments
        if process_cmd.startswith('"'):
            # Extract quoted executable
            end_quote = process_cmd.find('"', 1)
            exe_path = process_cmd[1:end_quote] if end_quote > 0 else process_cmd[1:]
        else:
            # Take first space-separated part
            exe_path = process_cmd.split()[0] if " " in process_cmd else process_cmd

        # Get just the filename
        return os.path.basename(exe_path)

    return None


def normalize_device_action(action: str | None) -> str | None:
    """Normalize device action to DeviceAction enum values.

    Args:
        action: Action value from Splunk

    Returns:
        Normalized DeviceAction enum value or None
    """
    if not action:
        return None

    action_lower = str(action).lower()

    # Map to DeviceAction enum values
    mapping = {
        "allowed": "allowed",
        "allow": "allowed",
        "permit": "allowed",
        "blocked": "blocked",
        "block": "blocked",
        "deny": "blocked",
        "denied": "blocked",
        "detected": "detected",
        "detect": "detected",
        "quarantined": "quarantined",
        "quarantine": "quarantined",
        "terminated": "terminated",
        "terminate": "terminated",
        "kill": "terminated",
        "killed": "terminated",
        "created": "allowed",  # API token creation, account creation
        "create": "allowed",
        "modified": "allowed",
        "updated": "allowed",
        "deleted": "blocked",
        "removed": "blocked",
    }

    return mapping.get(action_lower, "unknown")


def extract_web_info(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extract web-specific information from event.

    Uses standard WebInfo schema field names:
    - url, uri_path, uri_query
    - http_method, http_status, http_referrer, http_content_type
    - user_agent, bytes_in, bytes_out
    - category, action

    Args:
        event: Splunk notable event

    Returns:
        Web information dictionary or None
    """
    web_info = {}

    # Map web-specific fields to standard WebInfo schema field names
    web_fields = {
        # HTTP method
        "http_method": "http_method",
        "method": "http_method",
        # User agent
        "user_agent": "user_agent",
        "http_user_agent": "user_agent",
        # HTTP referrer
        "http_referrer": "http_referrer",
        "referrer": "http_referrer",
        # HTTP status
        "http_status": "http_status",
        # Note: "status" in Splunk notables is review status, not HTTP status
        # Byte counts
        "bytes_out": "bytes_out",
        "bytes_in": "bytes_in",
        # Content type
        "http_content_type": "http_content_type",
        "content_type": "http_content_type",
        # Extra fields (extra="allow" will handle these)
        "cookie": "cookie",
    }

    for event_field, info_field in web_fields.items():
        if event.get(event_field):
            web_info[info_field] = event[event_field]

    # Handle URL vs path: use url for full URLs, uri_path for paths
    # Always extract uri_path even from full URLs
    url_value = event.get("requested_url") or event.get("url")
    if url_value:
        if url_value.startswith(("http://", "https://", "ftp://")):
            web_info["url"] = url_value
            # Also extract the path component from the URL
            from urllib.parse import urlparse

            parsed = urlparse(url_value)
            if parsed.path:
                path_with_query = parsed.path
                if parsed.query:
                    path_with_query += "?" + parsed.query
                web_info["uri_path"] = path_with_query
        else:
            # It's a path (e.g., "/api/users"), not a full URL
            web_info["uri_path"] = url_value

    # Only return if we found web-related data
    return web_info if web_info else None


def _parse_pid(value: Any) -> int | None:
    """Parse PID value from string, handling hex values like '0x9ac'."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            # Try parsing as hex first (0x prefix)
            if value.lower().startswith("0x"):
                return int(value, 16)
            # Otherwise parse as decimal
            return int(value)
        except ValueError:
            return None
    return None


def extract_process_info(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extract process-specific information from event.

    Uses standard ProcessInfo schema field names:
    - process_name, process_path, process_id, process_guid, process_cmd
    - parent_process_name, parent_process_path, parent_process_id, parent_process_cmd
    - process_hash_md5, process_hash_sha1, process_hash_sha256

    Args:
        event: Splunk notable event

    Returns:
        Process information dictionary or None
    """
    process_info = {}

    # Map process-specific fields to standard ProcessInfo schema field names
    process_fields = {
        # Process command line
        "process": "cmd",
        "command_line": "cmd",
        # Process name and path
        "process_name": "name",
        "process_path": "path",
        # Process IDs (handled separately for hex parsing)
        "process_guid": "guid",
        # Parent process fields
        "parent_process": "parent_cmd",
        "parent_command_line": "parent_cmd",
        "parent_process_name": "parent_name",
        "parent_process_path": "parent_path",
        "parent_process_guid": "parent_guid",
        # Hash fields - Splunk often doesn't specify hash type, assume MD5 for generic
        "process_hash": "hash_md5",
        "file_hash": "hash_md5",
        # Extra fields (extra="allow" will handle these)
        "process_exec": "executable",
        "creator_process_name": "creator_name",
    }

    for event_field, info_field in process_fields.items():
        if event.get(event_field):
            process_info[info_field] = event[event_field]

    # Handle PID fields separately (may be hex like "0x9ac")
    pid_fields = {
        "process_id": "pid",
        "pid": "pid",
        "parent_process_id": "parent_pid",
        "parent_pid": "parent_pid",
    }

    for event_field, info_field in pid_fields.items():
        if event.get(event_field):
            parsed_pid = _parse_pid(event[event_field])
            if parsed_pid is not None:
                process_info[info_field] = parsed_pid

    # Only return if we found process-related data
    return process_info if process_info else None


def extract_cve_info(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extract CVE information from event.

    Args:
        event: Splunk notable event

    Returns:
        CVE information dictionary or None
    """

    cve_info: dict[str, Any] = {}
    cve_ids: set[str] = set()  # Use set to avoid duplicates

    # CVE pattern: CVE-YYYY-NNNNN (where N is 4 or more digits)
    cve_pattern = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

    # Fields to search for CVE references
    fields_to_search = [
        "rule_name",
        "rule_title",
        "rule_description",
        "search_name",
        "savedsearch_description",
        "threat_name",
        "signature",
        "alert_type",
        "_raw",  # Sometimes CVEs are in the raw data
    ]

    # Search for CVE IDs in various fields
    for field in fields_to_search:
        if event.get(field):
            field_value = str(event[field])
            found_cves = cve_pattern.findall(field_value)
            for cve in found_cves:
                cve_ids.add(cve.upper())  # Normalize to uppercase

    # Check MITRE annotations for CVE references
    if "annotations" in event:
        annotations_str = str(event["annotations"])
        found_cves = cve_pattern.findall(annotations_str)
        for cve in found_cves:
            cve_ids.add(cve.upper())

    # Special handling for known CVE-related fields
    if event.get("cve"):
        cve_ids.add(str(event["cve"]).upper())

    # If we found CVEs, structure the info
    if cve_ids:
        cve_info["ids"] = sorted(cve_ids)  # Convert set to sorted list

        # Check if this appears to be an active exploitation based on context
        exploitation_keywords = [
            "exploitation",
            "exploit",
            "exploited",
            "attack",
            "compromise",
        ]
        for field in ["rule_description", "rule_title", "savedsearch_description"]:
            if event.get(field):
                field_lower = str(event[field]).lower()
                if any(keyword in field_lower for keyword in exploitation_keywords):
                    cve_info["exploitation_context"] = True
                    break

    # Only return if we found CVE data
    return cve_info if cve_info else None


def extract_other_activities(event: dict[str, Any]) -> dict[str, Any] | None:
    """Extract additional context that doesn't fit other categories.

    Args:
        event: Splunk notable event

    Returns:
        Other activities dictionary or None
    """
    other_activities = {}

    # Fields that provide additional context
    other_fields = {
        "file_name": "file_name",
        "file_path": "file_path",
        "file_hash": "file_hash",
        "registry_path": "registry_path",
        "registry_value_name": "registry_value",
        "registry_value_data": "registry_data",
        "service_name": "service_name",
        "vendor_account": "vendor_account",
        "app": "application",
        "signature": "signature",
        "signature_id": "signature_id",
        "threat_name": "threat_name",
        "mitre_technique": "mitre_technique",
    }

    for event_field, info_field in other_fields.items():
        if event.get(event_field):
            other_activities[info_field] = event[event_field]

    # Only return if we found additional data
    return other_activities if other_activities else None


def extract_user_from_risk_entities(
    obj: dict[str, Any] | None, field_name: str
) -> str | None:
    """Extract specific user field from risk entities.

    Args:
        obj: Alert object (NAS format)
        field_name: Field name to look for (src_user or dest_user)

    Returns:
        User value or None
    """
    if not obj or not obj.get("risk_entities"):
        return None

    for entity in obj["risk_entities"]:
        # Look for the specific user field
        if entity.get("source_field") == field_name and entity.get("type") == "user":
            return entity.get("value")

    return None


def extract_all_iocs_with_primary(event: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Extract all IOCs including the primary IOC without duplication.

    This ensures the primary IOC is included in the IOCs list,
    similar to how primary risk entity is included in risk_entities.

    Args:
        event: Splunk notable event

    Returns:
        List of IOCs including primary if not already present
    """
    # First get all IOCs from the event
    iocs = extract_all_iocs(event) or []

    # Check if we have a primary IOC from the extraction
    primary_ioc = extract_primary_ioc(event)
    primary_type = determine_ioc_type(event)

    if primary_ioc and primary_type:
        # Check if this primary IOC is already in the list
        ioc_values = {ioc.get("value") for ioc in iocs}

        if primary_ioc not in ioc_values:
            # Skip internal IPs - they're our assets, not IOCs
            from alert_normalizer.mappers.splunk_notable_lists import (
                is_ip_address,
                is_private_ip,
            )

            if is_ip_address(primary_ioc) and is_private_ip(primary_ioc):
                pass  # Don't add internal IPs as IOCs
            else:
                # Add the primary IOC with high confidence since it was explicitly identified
                iocs.insert(
                    0,
                    {
                        "value": primary_ioc,
                        "type": primary_type,
                        "source_field": "primary_ioc",
                        "confidence": 90,  # High confidence (0-100 scale)
                    },
                )

    return iocs if iocs else None


def extract_risk_object_from_nas(
    obj: dict[str, Any] | None, normalized: bool = False
) -> str | None:
    """Extract risk object from NAS format for Notable reconstruction.

    Args:
        obj: Alert object (NAS format)
        normalized: If True, return normalized_risk_object value

    Returns:
        Risk object value or None
    """
    if not obj:
        return None

    # Check if we have risk entities list
    if obj.get("risk_entities"):
        for entity in obj["risk_entities"]:
            # Look for the original risk object fields
            if (
                normalized and entity.get("source_field") == "normalized_risk_object"
            ) or (not normalized and entity.get("source_field") == "risk_object"):
                return entity.get("value")

    # Fall back to primary risk entity only for non-normalized
    if not normalized and obj.get("primary_risk_entity_value"):
        return obj.get("primary_risk_entity_value")

    return None


def extract_risk_object_type_from_nas(obj: dict[str, Any] | None) -> str | None:
    """Extract risk object type from NAS format for Notable reconstruction.

    Args:
        obj: Alert object (NAS format)

    Returns:
        Risk object type or None
    """
    if not obj:
        return None

    # Check if we have risk entities list
    if obj.get("risk_entities"):
        for entity in obj["risk_entities"]:
            # Look for risk_object or normalized_risk_object
            if entity.get("source_field") in ["risk_object", "normalized_risk_object"]:
                entity_type = entity.get("type")
                # Map our entity types back to Splunk risk_object_type
                if entity_type == "user":
                    return "user"
                if entity_type == "file":
                    return "file_hash"
                return "system"

    # Fall back to primary risk entity type
    if obj.get("primary_risk_entity_type"):
        entity_type = obj.get("primary_risk_entity_type")
        if entity_type in ["user", _ENTITY_USER, "user"]:
            return "user"
        return "system"

    return None


def create_splunk_raw_field(obj: dict[str, Any]) -> str:
    """Create _raw field in Splunk's key=value format.

    Args:
        obj: Alert object

    Returns:
        Formatted _raw string for Splunk
    """
    import time
    from datetime import datetime

    # Get timestamp
    event_time = obj.get("triggering_event_time")
    if event_time:
        try:
            # Parse ISO format and convert to epoch
            if isinstance(event_time, str):
                dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
                epoch_time = int(dt.timestamp())
            else:
                epoch_time = int(time.time())
        except Exception:
            epoch_time = int(time.time())
    else:
        epoch_time = int(time.time())

    # Get rule name
    rule_name = obj.get("rule_name") or obj.get("title", "Unknown Alert")

    # Create the key=value format that Splunk expects
    # Start with timestamp and search_name like the working example
    raw_parts = [str(epoch_time), f'search_name="{rule_name}"']

    # Add other important fields in key=value format
    if obj.get("severity"):
        raw_parts.append(f'severity="{obj.get("severity")}"')

    if obj.get("source_vendor"):
        raw_parts.append(f'vendor="{obj.get("source_vendor")}"')

    if obj.get("primary_risk_entity_value"):
        entity_type = obj.get("primary_risk_entity_type", "unknown")
        if entity_type in ["device", "host"]:
            raw_parts.append(f'dest="{obj.get("primary_risk_entity_value")}"')
        elif entity_type == "user":
            raw_parts.append(f'user="{obj.get("primary_risk_entity_value")}"')

    if obj.get("primary_ioc_value"):
        raw_parts.append(f'threat_object="{obj.get("primary_ioc_value")}"')

    # Join with comma and space like Splunk expects
    return ", ".join(raw_parts)
