"""
Detailed analysis of individual notables - comparing raw vs normalized.
"""

import json
from pathlib import Path

from alert_normalizer.splunk import SplunkNotableNormalizer


def analyze_notable_detail(notable_index=0):  # noqa: C901
    """Analyze a single notable in detail."""

    # Load notable
    repo_path = Path(
        "/Users/imarios/Projects/splunk_notables_repo/unique_notables_all_time_strt_content.json"
    )

    notables = []
    with open(repo_path) as f:
        for line in f:
            if line.strip():
                notable_data = json.loads(line)
                if "result" in notable_data:
                    notables.append(notable_data["result"])

    if notable_index >= len(notables):
        print(f"Only {len(notables)} notables available")
        return None

    notable = notables[notable_index]

    print("=" * 80)
    print(f"NOTABLE #{notable_index + 1} - RAW SPLUNK FIELDS")
    print("=" * 80)

    # Show all fields present in the notable
    print(f"\nTotal fields in notable: {len(notable)}")

    # Group fields by category for better understanding
    field_categories = {
        "Core Alert Fields": [
            "rule_name",
            "rule_title",
            "rule_description",
            "_time",
            "severity",
            "urgency",
            "priority",
            "security_domain",
        ],
        "Source/Dest": [
            "src",
            "dest",
            "src_ip",
            "dest_ip",
            "src_port",
            "dest_port",
            "src_user",
            "dest_user",
            "user",
        ],
        "Process Fields": [
            "process",
            "process_name",
            "process_path",
            "parent_process",
            "parent_process_name",
            "parent_process_path",
            "process_id",
            "parent_process_id",
        ],
        "Web Fields": [
            "requested_url",
            "http_method",
            "user_agent",
            "http_status",
            "url",
            "uri_path",
            "uri_query",
        ],
        "Action/Status": ["action", "status", "status_label", "disposition"],
        "Risk Fields": ["risk_score", "risk_object", "risk_object_type"],
        "Notable Metadata": ["event_id", "notable_type", "owner", "owner_realname"],
        "Annotations": ["annotations", "annotations.mitre_attack"],
    }

    for category, fields in field_categories.items():
        present_fields = {f: notable.get(f) for f in fields if f in notable}
        if present_fields:
            print(f"\n{category}:")
            for field, value in present_fields.items():
                if value is not None:
                    value_str = (
                        str(value)[:100]
                        if not isinstance(value, int | float)
                        else value
                    )
                    print(f"  {field}: {value_str}")

    # Show any other fields not categorized
    all_categorized = set()
    for fields in field_categories.values():
        all_categorized.update(fields)

    other_fields = {
        k: v for k, v in notable.items() if k not in all_categorized and v is not None
    }
    if other_fields:
        print(f"\nOther Fields ({len(other_fields)} fields):")
        for field in sorted(other_fields.keys())[:20]:  # Show first 20
            value = other_fields[field]
            value_str = (
                str(value)[:100] if not isinstance(value, int | float | bool) else value
            )
            print(f"  {field}: {value_str}")

    # Now normalize and compare
    print("\n" + "=" * 80)
    print("NORMALIZED TO NAS")
    print("=" * 80)

    normalizer = SplunkNotableNormalizer()
    alert = normalizer.to_alertcreate(notable)

    # Show what we extracted
    alert_dict = alert.model_dump()

    print("\nExtracted Fields:")
    for field, value in alert_dict.items():
        if value is not None:
            if isinstance(value, dict):
                print(f"  {field}: {list(value.keys()) if value else 'empty dict'}")
            elif isinstance(value, str) and len(value) > 100:
                print(f"  {field}: {value[:100]}...")
            else:
                print(f"  {field}: {value}")

    # Analysis questions
    print("\n" + "=" * 80)
    print("ANALYSIS QUESTIONS")
    print("=" * 80)

    questions = []

    # Check for missed extractions
    if "action" in notable and not alert_dict.get("device_action"):
        questions.append(
            f"❓ Notable has 'action': '{notable['action']}' but device_action not extracted"
        )

    if "user" in notable and not alert_dict.get("primary_risk_entity_value"):
        questions.append(
            f"❓ Notable has 'user': '{notable['user']}' but not used as primary_risk_entity"
        )

    if "risk_object" in notable:
        questions.append(
            f"❓ Notable has 'risk_object': '{notable['risk_object']}' - should we use this?"
        )

    if "status" in notable:
        questions.append(
            f"❓ Notable has 'status': {notable['status']} - should we capture this?"
        )

    if "owner" in notable and notable["owner"] != "unassigned":
        questions.append(
            f"❓ Notable has 'owner': '{notable['owner']}' - should we capture assignment?"
        )

    # Check security domain mapping
    if notable.get("security_domain") == "threat" and not alert_dict.get(
        "source_category"
    ):
        questions.append("❓ Security domain 'threat' not mapped to source_category")

    # Check for annotations
    if (
        "annotations" in notable
        and isinstance(notable["annotations"], dict)
        and "mitre_attack" in notable["annotations"]
    ):
        questions.append(
            "❓ Has MITRE ATT&CK annotations - should we extract tactics/techniques?"
        )

    # Check if we missed any network data
    network_fields = ["src", "src_ip", "dest", "dest_ip", "src_port", "dest_port"]
    has_network = any(f in notable for f in network_fields)
    if has_network and not alert_dict.get("network_info"):
        questions.append("❓ Has network fields but network_info is empty/None")

    if questions:
        for q in questions:
            print(q)
    else:
        print("✅ No obvious gaps found")

    return notable, alert


if __name__ == "__main__":
    # Analyze first notable
    print("Analyzing Notable #1")
    print()
    notable, alert = analyze_notable_detail(0)
