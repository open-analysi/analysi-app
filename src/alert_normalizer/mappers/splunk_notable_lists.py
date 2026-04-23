"""Extract lists of entities and IOCs from Splunk notables - Version 2.

This version properly differentiates between:
- Risk Entities: Our assets at risk (our users, devices, internal IPs)
- IOCs: Threat indicators (malicious IPs, domains, hashes, attack tools)
"""

import ipaddress
from typing import Any

# Central list of invalid/placeholder values used across the codebase
INVALID_VALUES = {
    "",
    "0",
    "-",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "undefined",
    "empty",
    ".",
    "_",
    "not_mapped",
    "none_mapped",
}


def is_ip_address(value: str) -> bool:
    """Check if a value is an IP address."""
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/internal."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except (ValueError, AttributeError):
        return False


def is_public_ip(ip_str: str) -> bool:
    """Check if an IP address is public/external."""
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


def is_valid_user(value: str) -> bool:
    """Check if a user value is valid (not a placeholder or missing data indicator).

    Args:
        value: User value to validate

    Returns:
        True if the user value appears to be valid, False otherwise
    """
    if not value:
        return False

    # Clean the value
    cleaned = value.strip().lower()

    # Check if it's an invalid value using the shared constant
    if cleaned in INVALID_VALUES:
        return False

    # Check if it's just numbers (like "0", "1", "123")
    return not cleaned.isdigit()


def extract_all_risk_entities(event: dict[str, Any]) -> list[dict[str, Any]] | None:  # noqa: C901
    """Extract all risk entities (our assets at risk) from a Splunk notable.

    Risk entities are OUR assets that are at risk:
    - Our users
    - Our devices/systems
    - Our internal IP addresses

    Uses standard RiskEntity schema field names:
    - entity_type, entity_value (required)
    - source_field, context (extra fields)

    Args:
        event: Splunk notable event

    Returns:
        List of risk entities with type and metadata
    """
    entities = []
    seen = set()

    # User entities - these are always our users
    user_fields = []

    # Check if risk_object is a user - add BOTH normalized and raw if they differ
    if event.get("risk_object_type") == "user":
        if event.get("normalized_risk_object"):
            user_fields.append(("normalized_risk_object", "user"))
        if event.get("risk_object") and event.get("risk_object") != event.get(
            "normalized_risk_object"
        ):
            user_fields.append(("risk_object", "user"))

    # Standard user fields - these typically represent our users
    user_fields.extend(
        [
            ("user", "user"),
            ("src_user", "user"),  # Source user is typically ours
            ("dest_user", "user"),  # Destination user on our systems
            ("src_user_name", "user"),
            ("dest_user_name", "user"),
            ("account", "user"),
            ("account_name", "user"),
            # Note: sender/recipient could be external in email scenarios
        ]
    )

    for field, entity_type in user_fields:
        if event.get(field):
            value = str(event[field]).strip()
            # Clean up values
            if "\\nNONE_MAPPED" in value:
                value = value.split("\\nNONE_MAPPED")[0]
            # Only add valid user values
            if value and value not in seen and is_valid_user(value):
                seen.add(value)
                entities.append(
                    {
                        "value": value,
                        "type": entity_type,
                        "source_field": field,
                        "context": "internal_user",
                    }
                )

    # Device/hostname entities - our systems
    device_fields = []

    # Check if risk_object is a system/device - add BOTH normalized and raw if they differ
    if event.get("risk_object_type") in ["system", "device", "other"]:
        if event.get("normalized_risk_object"):
            device_fields.append(("normalized_risk_object", "device"))
        if event.get("risk_object") and event.get("risk_object") != event.get(
            "normalized_risk_object"
        ):
            device_fields.append(("risk_object", "device"))

    # Also check for file_hash risk objects (they go to IOCs but also track as entity)
    if event.get("risk_object_type") == "file_hash":
        if event.get("normalized_risk_object"):
            device_fields.append(("normalized_risk_object", "file"))
        if event.get("risk_object") and event.get("risk_object") != event.get(
            "normalized_risk_object"
        ):
            device_fields.append(("risk_object", "file"))

    # Fields that typically represent our devices
    device_fields.extend(
        [
            ("dest", "device"),  # Destination is often our system
            ("dest_host", "device"),
            ("ComputerName", "device"),
            ("server", "device"),
            # src could be our system in outbound connection scenarios
            ("src", "device"),  # Only if it's our system
            ("src_host", "device"),
        ]
    )

    for field, entity_type in device_fields:
        if event.get(field):
            value = str(event[field]).strip()
            # Check if it's a hostname (not an IP or URL)
            if (
                value
                and not is_ip_address(value)
                and not value.startswith("http")
                and is_internal_hostname(value)
                and value not in seen
            ):
                seen.add(value)
                entities.append(
                    {
                        "value": value,
                        "type": entity_type,
                        "source_field": field,
                        "context": "internal_device",
                    }
                )

    # Internal IP addresses - our network
    ip_fields = [
        ("src_ip", "ip"),
        ("dest_ip", "ip"),
        ("src", "ip"),
        ("dest", "ip"),
        ("client_ip", "ip"),
        ("server_ip", "ip"),
        ("local_ip", "ip"),
        ("internal_ip", "ip"),
    ]

    for field, entity_type in ip_fields:
        if event.get(field):
            value = str(event[field]).strip()
            if is_ip_address(value) and is_private_ip(value) and value not in seen:
                seen.add(value)
                entities.append(
                    {
                        "value": value,
                        "type": entity_type,
                        "source_field": field,
                        "context": "internal_ip",
                    }
                )

    return entities if entities else None


def extract_all_iocs(event: dict[str, Any]) -> list[dict[str, Any]] | None:  # noqa: C901
    """Extract all IOCs (threat indicators) from a Splunk notable.

    IOCs are indicators of compromise - evidence of threat actor activity:
    - External/malicious IP addresses
    - Malicious domains/URLs
    - Malware hashes
    - Malicious processes/tools
    - Attack patterns

    Args:
        event: Splunk notable event

    Returns:
        List of IOCs with type and metadata
    """
    iocs = []
    seen = set()

    # Threat object field - explicitly marked as threat
    if event.get("threat_object"):
        value = str(event["threat_object"]).strip()
        threat_type = event.get("threat_object_type", "unknown")

        if value and value not in seen:
            # Skip internal IPs - they're our assets, not IOCs
            if is_ip_address(value) and is_private_ip(value):
                pass  # Don't add internal IPs as IOCs
            else:
                seen.add(value)
                ioc_type = map_threat_type(threat_type)
                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": "threat_object",
                        "confidence": 90,  # Explicitly marked as threat (0-100 scale)
                    }
                )

    # External IP addresses (potential C2, attackers)
    ip_fields = [
        ("src_ip", "ip"),
        ("dest_ip", "ip"),
        ("src", "ip"),
        ("dest", "ip"),
        ("attacker_ip", "ip"),
        ("malicious_ip", "ip"),
        ("c2_ip", "ip"),
        ("remote_ip", "ip"),
    ]

    for field, ioc_type in ip_fields:
        if event.get(field):
            value = str(event[field]).strip()
            # Add all external IPs as IOCs (they're potential threats)
            if is_ip_address(value) and is_public_ip(value) and value not in seen:
                seen.add(value)
                # Higher confidence if explicitly marked or blocked (0-100 scale)
                confidence = 90 if is_likely_malicious_ip(event, field, value) else 70
                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": field,
                        "confidence": confidence,
                    }
                )

    # URLs (any external URL could be an IOC)
    url_fields = [
        ("requested_url", "url"),
        ("url", "url"),
        ("uri", "url"),
        ("malicious_url", "url"),
        ("phishing_url", "url"),
        ("http_referrer", "url"),
        ("referrer", "url"),
        ("src", "url"),  # src can contain URLs
        ("dest", "url"),  # dest can contain URLs
    ]

    for field, ioc_type in url_fields:
        if event.get(field):
            value = str(event[field]).strip()
            # Include all external URLs as potential IOCs
            if (
                value
                and value.startswith(("http://", "https://", "ftp://"))
                and value not in seen
            ):
                seen.add(value)
                # Higher confidence if suspicious or explicitly marked (0-100 scale)
                confidence = (
                    90 if (is_suspicious_url(value) or "malicious" in field) else 70
                )
                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": field,
                        "confidence": confidence,
                    }
                )

    # External domains (potential C2, phishing, etc)
    domain_fields = [
        ("domain", "domain"),
        ("dns_query", "domain"),
        ("query", "domain"),
        ("malicious_domain", "domain"),
        ("c2_domain", "domain"),
        ("dest", "domain"),  # If dest contains a domain
        ("src", "domain"),  # If src contains a domain
    ]

    for field, ioc_type in domain_fields:
        if event.get(field):
            value = str(event[field]).strip()
            # Check if it's a domain (has dots, not an IP, not internal)
            if (
                value
                and "." in value
                and not is_ip_address(value)
                and not is_internal_domain(value)
                and value not in seen
                and not value.startswith("http")
            ):
                seen.add(value)
                # 0-100 confidence scale
                confidence = 90 if "malicious" in field or "c2" in field else 70
                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": field,
                        "confidence": confidence,
                    }
                )

    # User agents - extract from all Notable events
    # POLICY: Notables are already filtered alerts, so any user_agent is worth preserving
    # Better to include it than miss a legitimate IOC
    user_agent_fields = [
        ("user_agent", "user_agent"),
        ("http_user_agent", "user_agent"),
        ("UserAgent", "user_agent"),
        ("cs_user_agent", "user_agent"),
    ]

    for field, ioc_type in user_agent_fields:
        if event.get(field):
            value = str(event[field]).strip()
            if value and value not in seen:
                seen.add(value)
                # High confidence if suspicious, medium otherwise (0-100 scale)
                confidence = 90 if is_suspicious_user_agent(value) else 70
                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": field,
                        "confidence": confidence,
                    }
                )

    # File hashes - almost always IOCs when present
    hash_fields = [
        ("file_hash", "filehash"),
        ("md5", "filehash"),
        ("sha1", "filehash"),
        ("sha256", "filehash"),
        ("hash", "filehash"),
    ]

    for field, ioc_type in hash_fields:
        if event.get(field):
            value = str(event[field]).strip()
            if value and is_hash_format(value) and value not in seen:
                seen.add(value)
                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": field,
                        "hash_type": detect_hash_type(value),
                        "confidence": 90,  # Hashes are usually IOCs (0-100 scale)
                    }
                )

    # Processes (include all as potential IOCs, with confidence levels)
    process_fields = [
        ("process", "process"),
        ("process_name", "process"),
        ("command_line", "process"),
        ("parent_process", "process"),
    ]

    for field, ioc_type in process_fields:
        if event.get(field):
            value = str(event[field]).strip()
            if value and value not in seen:
                seen.add(value)
                # Determine confidence based on process characteristics (0-100 scale)
                if is_suspicious_process(value):
                    confidence = 90 if not is_dual_use_tool(value) else 70
                elif is_dual_use_tool(value):
                    confidence = 50  # Legitimate tool but could be abused
                else:
                    confidence = 50  # Unknown process

                iocs.append(
                    {
                        "value": value,
                        "type": ioc_type,
                        "source_field": field,
                        "confidence": confidence,
                    }
                )

    # Note: CVEs are NOT IOCs - they're vulnerabilities that were exploited
    # CVE information is extracted separately in extract_cve_info() function
    # and stored in the cve_info field, not in the IOCs list

    return iocs if iocs else None


# Helper functions


def is_internal_hostname(hostname: str) -> bool:
    """Check if hostname belongs to internal infrastructure."""
    hostname_lower = hostname.lower()
    internal_patterns = [
        ".local",
        ".internal",
        ".corp",
        ".lan",
        "workstation",
        "desktop",
        "laptop",
        "dc-",
        "win-",
        "srv-",
        "server",
    ]
    return any(pattern in hostname_lower for pattern in internal_patterns)


def is_internal_domain(domain: str) -> bool:
    """Check if domain is internal."""
    domain_lower = domain.lower()
    internal_tlds = [".local", ".internal", ".corp", ".lan", "localhost"]
    return any(domain_lower.endswith(tld) for tld in internal_tlds)


def is_suspicious_user_agent(user_agent: str) -> bool:
    """Check if a user agent string is suspicious or malicious.

    Args:
        user_agent: User agent string to check

    Returns:
        True if the user agent appears suspicious
    """
    if not user_agent:
        return False

    ua_lower = user_agent.lower()

    # Known scanning/attack tools
    suspicious_patterns = [
        "zgrab",  # Scanner
        "sqlmap",  # SQL injection tool
        "nikto",  # Web vulnerability scanner
        "nmap",  # Network scanner
        "masscan",  # Port scanner
        "burp",  # Burp Suite
        "owasp",  # OWASP tools
        "acunetix",  # Vulnerability scanner
        "nessus",  # Vulnerability scanner
        "metasploit",  # Exploitation framework
        "havij",  # SQL injection tool
        "python-requests",  # Often used in scripts (context-dependent)
        "curl",  # Command line tool (context-dependent)
        "wget",  # Command line tool (context-dependent)
        "gobuster",  # Directory brute-forcer
        "dirb",  # Directory brute-forcer
        "wfuzz",  # Web fuzzer
        "hydra",  # Brute force tool
        "bot",  # Generic bot indicator
        "crawler",  # Generic crawler (context-dependent)
        "spider",  # Generic spider (context-dependent)
    ]

    for pattern in suspicious_patterns:
        if pattern in ua_lower:
            return True

    # Suspiciously short user agents
    if len(user_agent) < 10:
        return True

    # User agents that are just "Mozilla/5.0" or similar without browser info
    if user_agent in ["Mozilla/5.0", "Mozilla/4.0", "Mozilla"]:
        return True

    # Check for obvious spoofing attempts (malformed user agents)
    return bool("mozilla" in ua_lower and ua_lower.count("(") != ua_lower.count(")"))


def is_web_attack_context(event: dict[str, Any]) -> bool:
    """Check if the event appears to be a web attack based on context.

    Robust to typos and variations in attack type naming.

    Args:
        event: The notable event

    Returns:
        True if this appears to be a web attack context
    """
    # Check for web attack indicators in various fields
    attack_indicators = [
        "sql injection",
        "xss",
        "cross-site",
        "command injection",
        "path traversal",
        "directory traversal",
        "exploit",
        "cve-",
        "owasp",
        "payload",
        "powershell",
        "cmd.exe",
        "eval(",
        "exec(",
        "system(",
        "<script",
        "javascript:",
        "javascript",
        "onerror=",
        "web attack",
        "web application attack",
        "web attck",  # Handle known typo
        "scanner",
        "fuzzing",
        "<script",
        "$script",  # XSS patterns
    ]

    fields_to_check = [
        "rule_name",
        "rule_title",
        "rule_description",
        "search_name",
        "signature",
        "alert_type",
    ]

    for field in fields_to_check:
        if event.get(field):
            field_lower = str(event[field]).lower()
            for indicator in attack_indicators:
                if indicator in field_lower:
                    return True

            # Flexible check: "web" + "attack"/"attck" (handles spacing/typos)
            if "web" in field_lower and (
                "attack" in field_lower or "attck" in field_lower
            ):
                return True

    # Check if HTTP method is suspicious
    if event.get("http_method") in [
        "PUT",
        "DELETE",
        "PATCH",
        "OPTIONS",
        "TRACE",
        "CONNECT",
    ]:
        return True

    # Check if requested URL contains suspicious patterns
    if event.get("requested_url"):
        url_lower = str(event["requested_url"]).lower()
        url_attacks = [
            "../",
            "..\\",
            "%2e%2e",
            "eval(",
            "exec(",
            "<script",
            "cmd=",
            "command=",
        ]
        for pattern in url_attacks:
            if pattern in url_lower:
                return True

    return False


def is_suspicious_url(url: str) -> bool:
    """Check if URL appears suspicious."""
    url_lower = url.lower()

    # URLs with IP addresses instead of domains
    if url_lower.startswith("http://") and any(c.isdigit() for c in url[7:10]):
        return True

    # Suspicious TLDs
    suspicious_tlds = [".tk", ".ml", ".ga", ".cf", ".click", ".download"]
    if any(tld in url_lower for tld in suspicious_tlds):
        return True

    # Long random-looking subdomains (DGA-like)
    parts = url_lower.split(".")
    for part in parts:
        if len(part) > 20 and not any(
            word in part for word in ["amazon", "google", "microsoft"]
        ):
            return True

    return False


def is_suspicious_process(process: str) -> bool:
    """Check if process appears suspicious."""
    process_lower = process.lower()

    # Known attack tools
    attack_tools = [
        "mimikatz",
        "psexec",
        "procdump",
        "lazagne",
        "bloodhound",
        "rubeus",
        "cobalt",
        "empire",
        "metasploit",
        "nmap",
        "masscan",
    ]

    for tool in attack_tools:
        if tool in process_lower:
            return True

    # Suspicious command patterns
    suspicious_patterns = [
        "-enc ",
        "-encoded",
        "bypass",
        "hidden",
        "invoke-expression",
        "downloadstring",
        "frombase64",
        "/c ping",
        "/c whoami",
    ]

    for pattern in suspicious_patterns:
        if pattern in process_lower:
            return True

    # PowerShell/cmd with suspicious flags
    return bool(
        ("powershell" in process_lower or "cmd" in process_lower)
        and any(
            flag in process_lower
            for flag in ["-enc", "-e ", "-ec", "-ep bypass", "-nop", "-w hidden"]
        )
    )


def is_dual_use_tool(process: str) -> bool:
    """Check if process is a legitimate tool that can be abused."""
    process_lower = process.lower()
    dual_use = [
        "powershell",
        "cmd",
        "wmic",
        "rundll32",
        "regsvr32",
        "mshta",
        "certutil",
        "bitsadmin",
        "schtasks",
        "net",
        "reg",
        "sc",
    ]
    return any(tool in process_lower for tool in dual_use)


def is_likely_malicious_ip(event: dict, field: str, ip: str) -> bool:
    """Determine if an external IP is likely malicious based on context."""
    # If it's in a threat field, it's likely malicious
    if "threat" in field or "attack" in field or "malicious" in field:
        return True

    # If it's the destination of an outbound connection from a suspicious process
    if (
        field in ["dest_ip", "dest"]
        and event.get("process_name")
        and is_suspicious_process(str(event.get("process_name", "")))
    ):
        return True

    # If there's an action indicating blocking/detection
    return bool(
        event.get("action") in ["blocked", "detected", "prevented"]
        and field in ["src_ip", "src"]
    )


def is_hash_format(value: str) -> bool:
    """Check if value looks like a hash."""
    value = value.strip().lower()
    # Remove common prefixes
    for prefix in ["md5:", "sha1:", "sha256:"]:
        if value.startswith(prefix):
            value = value[len(prefix) :]

    # Check if it's hex and right length for common hashes
    if all(c in "0123456789abcdef" for c in value):
        return len(value) in [32, 40, 64, 128]
    return False


def detect_hash_type(hash_value: str) -> str | None:
    """Detect the type of hash based on length."""
    if not hash_value:
        return None

    hash_value = hash_value.strip().lower()

    # Remove common prefixes
    for prefix in ["md5:", "sha1:", "sha256:", "sha512:"]:
        if hash_value.startswith(prefix):
            return prefix[:-1]

    # Detect by length
    length = len(hash_value)

    if length == 32:
        return "md5"
    if length == 40:
        return "sha1"
    if length == 64:
        return "sha256"
    if length == 128:
        return "sha512"
    return "unknown"


def map_threat_type(threat_type: str) -> str:
    """Map Splunk threat type to IOC type."""
    mapping = {
        "hash": "filehash",
        "file_hash": "filehash",
        "ip": "ip",
        "domain": "domain",
        "url": "url",
        "email": "email",
        "process": "process",
        "registry": "registry",
    }
    return mapping.get(threat_type.lower(), "unknown")
