"""
Test script to process notables from repository and verify enhanced field extraction.
"""

import json
from pathlib import Path

from alert_normalizer.splunk import SplunkNotableNormalizer


def test_repository_notables():  # noqa: C901
    """Test normalization of notables from repository."""

    # Load notables from repository
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

    print(f"Total notables loaded: {len(notables)}")
    print("=" * 80)

    # Create normalizer
    normalizer = SplunkNotableNormalizer()

    # Process first 10 notables
    for i, notable in enumerate(notables[:10], 1):
        print(f"\n{'=' * 80}")
        print(f"NOTABLE {i}")
        print(f"{'=' * 80}")

        # Extract key fields for inspection
        print(f"Rule: {notable.get('rule_name', 'N/A')}")
        print(f"Time: {notable.get('_time', 'N/A')}")
        print(f"Severity: {notable.get('severity', 'N/A')}")
        print(f"Security Domain: {notable.get('security_domain', 'N/A')}")

        # Check for CVE references
        cve_fields = ["rule_name", "rule_title", "rule_description", "search_name"]
        for field in cve_fields:
            if notable.get(field):
                field_value = str(notable[field])
                if "CVE" in field_value.upper():
                    print(f"📌 CVE Reference in {field}: {field_value[:100]}")

        # Check for action field
        if "action" in notable:
            print(f"Action: {notable['action']}")

        # Check for web-related fields
        web_fields = ["requested_url", "http_method", "user_agent"]
        has_web = any(field in notable for field in web_fields)
        if has_web:
            print("🌐 Web fields present:")
            for field in web_fields:
                if field in notable:
                    print(f"  - {field}: {str(notable[field])[:100]}")

        # Check for process fields
        process_fields = ["process", "process_name", "parent_process"]
        has_process = any(field in notable for field in process_fields)
        if has_process:
            print("⚙️ Process fields present:")
            for field in process_fields:
                if field in notable:
                    print(f"  - {field}: {str(notable[field])[:100]}")

        # Normalize the notable
        try:
            alert = normalizer.to_alertcreate(notable)

            print("\n📊 NORMALIZED RESULTS:")
            print(f"  ✓ Title: {alert.title}")
            print(f"  ✓ Severity: {alert.severity}")
            print(f"  ✓ Source Category: {alert.source_category}")

            if alert.device_action:
                print(f"  ✓ Device Action: {alert.device_action}")

            if alert.source_event_id:
                print(f"  ✓ Source Event ID: {alert.source_event_id[:50]}...")

            if alert.cve_info:
                print(f"  ✓ CVE Info: {alert.cve_info}")

            if alert.web_info:
                print(f"  ✓ Web Info fields: {list(alert.web_info.keys())}")

            if alert.process_info:
                print(f"  ✓ Process Info fields: {list(alert.process_info.keys())}")

            if alert.network_info:
                print(f"  ✓ Network Info fields: {list(alert.network_info.keys())}")

            if alert.other_activities:
                print(
                    f"  ✓ Other Activities fields: {list(alert.other_activities.keys())}"
                )

            if alert.primary_ioc_value:
                print(
                    f"  ✓ Primary IOC: {alert.primary_ioc_value[:100]} (type: {alert.primary_ioc_type})"
                )

        except Exception as e:
            print(f"\n❌ ERROR during normalization: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    test_repository_notables()
