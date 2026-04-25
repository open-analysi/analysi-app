#!/usr/bin/env python3
"""
Build a hierarchical index of runbooks based on their YAML frontmatter.
Creates directory structure with categorized runbook lists for efficient filtering.
No external dependencies required - uses built-in Python only.

Usage:
    # Generate index in auto-created temp directory (prints INDEX_DIR=<path>)
    python3 build_runbook_index.py

    # Generate index in specific directory
    python3 build_runbook_index.py --output-dir /tmp/my-index

    # Specify custom runbooks source directory
    python3 build_runbook_index.py --runbooks-dir /path/to/runbooks --output-dir /tmp/index
"""

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from datetime import UTC
from pathlib import Path
from typing import Any


class RunbookIndexBuilder:
    def __init__(self, runbooks_dir: str, index_output_dir: str):
        self.runbooks_dir = Path(runbooks_dir)
        self.index_output_dir = Path(index_output_dir)
        self.runbooks = []

    def to_kebab_case(self, text: str) -> str:
        """Convert text to kebab-case for filenames."""
        # Replace spaces and underscores with hyphens
        text = text.replace(" ", "-").replace("_", "-")
        # Convert to lowercase
        text = text.lower()
        # Remove any characters that aren't alphanumeric or hyphens
        text = re.sub(r"[^a-z0-9-]", "", text)
        # Replace multiple consecutive hyphens with single hyphen
        text = re.sub(r"-+", "-", text)
        # Remove leading/trailing hyphens
        text = text.strip("-")
        return text

    def extract_yaml_frontmatter(self, file_path: Path) -> dict[str, Any]:
        """Extract YAML frontmatter from a markdown file using regex parsing."""
        with open(file_path) as f:
            content = f.read()

        # Match YAML frontmatter between --- markers
        yaml_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not yaml_match:
            return {}

        yaml_content = yaml_match.group(1)
        metadata = {}

        # Parse simple YAML fields manually
        # Handle single-line string values
        for match in re.finditer(r"^(\w+):\s*(.+?)$", yaml_content, re.MULTILINE):
            key = match.group(1)
            value = match.group(2).strip()
            # Remove quotes if present
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            metadata[key] = value

        # Handle array values (e.g., mitre_tactics: [T1190, T1059])
        for match in re.finditer(r"^(\w+):\s*\[(.*?)\]", yaml_content, re.MULTILINE):
            key = match.group(1)
            values = match.group(2)
            # Split by comma and clean up
            items = [
                v.strip().strip('"').strip("'") for v in values.split(",") if v.strip()
            ]
            metadata[key] = items

        # Handle multiline arrays (e.g., integrations_required:\n  - splunk\n  - virustotal)
        current_key = None
        for line in yaml_content.split("\n"):
            # Check for key with colon ending (potential list start)
            key_match = re.match(r"^(\w+):\s*$", line)
            if key_match:
                current_key = key_match.group(1)
                metadata[current_key] = []
            # Check for list items
            elif current_key and re.match(r"^\s*-\s+(.+)", line):
                item_match = re.match(r"^\s*-\s+(.+)", line)
                if item_match:
                    value = item_match.group(1).strip().strip('"').strip("'")
                    metadata[current_key].append(value)
            # Reset if we hit a new non-list key
            elif re.match(r"^[a-zA-Z]", line) and ":" in line:
                current_key = None

        return metadata

    def scan_runbooks(self):
        """Scan all .md files in runbooks directory and extract metadata."""
        runbook_files = list(self.runbooks_dir.glob("*.md"))

        for runbook_file in runbook_files:
            metadata = self.extract_yaml_frontmatter(runbook_file)
            if metadata:
                metadata["filename"] = runbook_file.name
                metadata["path"] = str(
                    runbook_file.relative_to(self.runbooks_dir.parent)
                )
                self.runbooks.append(metadata)

        print(f"Found {len(self.runbooks)} runbooks", file=sys.stderr)
        return self.runbooks

    def extract_vendor_product(self, detection_rule: str) -> tuple:
        """Extract vendor and product from CVE-related detection rules."""
        if not detection_rule:
            return ("unknown", "unknown")

        rule_lower = detection_rule.lower()

        # Common patterns: "Vendor Product Description CVE-YYYY-NNNN"
        # Extract vendor/product pairs
        vendor_products = {
            "palo alto": "pan-os",
            "checkpoint": "security-gateway",
            "atlassian": "confluence",
            "microsoft": "sharepoint",
            "exchange": "exchange",
            "fortinet": "fortigate",
            "cisco": "asa",
            "f5": "big-ip",
        }

        for vendor_key, product in vendor_products.items():
            if vendor_key in rule_lower:
                return (vendor_key.replace(" ", "_"), product)

        return ("other", "unknown")

    def build_indexes(self):
        """Build all index categories and write to files."""
        indexes = {
            "by_subcategory": defaultdict(list),
            "by_attack_type": defaultdict(list),
            "by_source_category": defaultdict(list),
            "by_mitre_tactic": defaultdict(list),
            "by_integration": defaultdict(list),
            "by_vendor": defaultdict(list),
            "by_cve_year": defaultdict(list),
        }

        for runbook in self.runbooks:
            # Index by subcategory (primary attack classifier)
            subcategory = runbook.get("subcategory", "unknown")
            indexes["by_subcategory"][subcategory].append(runbook)

            # Index by attack type (broad category like "Web Attack", "Brute Force")
            alert_type = runbook.get("alert_type", "unknown")
            indexes["by_attack_type"][alert_type].append(runbook)

            # Index by source category
            source_cat = runbook.get("source_category", "unknown")
            indexes["by_source_category"][source_cat].append(runbook)

            # Index by MITRE tactics
            mitre_tactics = runbook.get("mitre_tactics", [])
            for tactic in mitre_tactics:
                indexes["by_mitre_tactic"][tactic].append(runbook)

            # Index by required integrations
            integrations = runbook.get("integrations_required", [])
            for integration in integrations:
                indexes["by_integration"][integration].append(runbook)

            # For CVE-related runbooks
            detection_rule = runbook.get("detection_rule", "")
            if "CVE-" in detection_rule or "cve-" in detection_rule.lower():
                # Extract CVE year
                cve_match = re.search(r"CVE-(\d{4})-\d+", detection_rule, re.IGNORECASE)
                if cve_match:
                    year = cve_match.group(1)
                    indexes["by_cve_year"][year].append(runbook)

                # Extract vendor/product
                vendor, product = self.extract_vendor_product(detection_rule)
                indexes["by_vendor"][vendor].append(runbook)

        return indexes

    def write_index_files(self, indexes: dict[str, dict[str, list]]):
        """Write index files to directory structure."""
        from datetime import datetime

        # Create index directory
        self.index_output_dir.mkdir(parents=True, exist_ok=True)

        # Get current timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Write master index
        master_index = {
            "total_runbooks": len(self.runbooks),
            "categories": {},
            "generated_at": timestamp,
        }

        for category, subcategories in indexes.items():
            category_dir = self.index_output_dir / category
            category_dir.mkdir(exist_ok=True)

            master_index["categories"][category] = list(subcategories.keys())

            for subcat, runbooks in subcategories.items():
                # Create markdown file for this subcategory (kebab-case)
                kebab_subcat = self.to_kebab_case(subcat)
                md_file = category_dir / f"{kebab_subcat}.md"

                with open(md_file, "w") as f:
                    # Add auto-generated header
                    f.write("<!--\n")
                    f.write("AUTOMATICALLY GENERATED INDEX FILE\n")
                    f.write("DO NOT MANUALLY EDIT THIS FILE\n")
                    f.write(f"Generated: {timestamp}\n")
                    f.write("Source: build_runbook_index.py\n")
                    f.write("-->\n\n")

                    f.write(f"# {category}/{subcat} Runbooks\n\n")
                    f.write(f"**Count:** {len(runbooks)} runbooks\n")
                    f.write(f"**Generated:** {timestamp}\n\n")

                    for runbook in runbooks:
                        f.write(f"## {runbook['filename']}\n")
                        f.write(
                            f"- **Detection Rule:** {runbook.get('detection_rule', 'N/A')}\n"
                        )
                        f.write(
                            f"- **Alert Type:** {runbook.get('alert_type', 'N/A')}\n"
                        )
                        f.write(
                            f"- **Subcategory:** {runbook.get('subcategory', 'N/A')}\n"
                        )
                        f.write(
                            f"- **Source Category:** {runbook.get('source_category', 'N/A')}\n"
                        )
                        f.write(
                            f"- **MITRE Tactics:** {', '.join(runbook.get('mitre_tactics', []))}\n"
                        )
                        f.write(f"- **Path:** `{runbook['path']}`\n\n")

        # Write master index JSON with metadata
        master_index_file = self.index_output_dir / "master_index.json"
        master_index["_metadata"] = {
            "auto_generated": True,
            "do_not_edit": "This file is automatically generated. Manual edits will be overwritten.",
            "generated_at": timestamp,
            "generator": "build_runbook_index.py",
        }
        with open(master_index_file, "w") as f:
            json.dump(master_index, f, indent=2)

        # Write complete runbook metadata JSON with header
        runbooks_data = {
            "_metadata": {
                "auto_generated": True,
                "do_not_edit": "This file is automatically generated. Manual edits will be overwritten.",
                "generated_at": timestamp,
                "generator": "build_runbook_index.py",
            },
            "runbooks": self.runbooks,
        }
        runbooks_json_file = self.index_output_dir / "all_runbooks.json"
        with open(runbooks_json_file, "w") as f:
            json.dump(runbooks_data, f, indent=2)

        print(f"Index files written to {self.index_output_dir}", file=sys.stderr)
        for category, subcats in indexes.items():
            print(f"  {category}: {len(subcats)} subcategories", file=sys.stderr)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Build hierarchical index of runbooks from YAML frontmatter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Auto-generate temp directory for index
    python3 build_runbook_index.py

    # Specify output directory
    python3 build_runbook_index.py --output-dir /tmp/runbook-index

    # Specify both source and output directories
    python3 build_runbook_index.py --runbooks-dir ./repository --output-dir /tmp/index
        """,
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for index files. If not specified, creates a temp directory.",
    )
    parser.add_argument(
        "--runbooks-dir",
        help="Source directory containing runbook .md files. Defaults to repository/ in skill directory.",
    )
    args = parser.parse_args()

    # Determine runbooks source directory
    script_dir = Path(__file__).parent
    skill_dir = script_dir.parent

    if args.runbooks_dir:
        runbooks_dir = Path(args.runbooks_dir)
    else:
        runbooks_dir = skill_dir / "repository"

    # Determine output directory (temp if not specified)
    if args.output_dir:
        index_output_dir = Path(args.output_dir)
    else:
        index_output_dir = Path(tempfile.mkdtemp(prefix="runbook-index-"))

    print(f"Scanning runbooks in: {runbooks_dir}", file=sys.stderr)
    print(f"Building index in: {index_output_dir}", file=sys.stderr)

    # Build the index
    builder = RunbookIndexBuilder(runbooks_dir, index_output_dir)
    builder.scan_runbooks()
    indexes = builder.build_indexes()
    builder.write_index_files(indexes)

    print("\nIndex building complete!", file=sys.stderr)
    print(f"Categories created: {list(indexes.keys())}", file=sys.stderr)

    # Output the index directory path in parseable format (to stdout)
    # This allows agents to capture the path: INDEX_DIR=$(python3 build_runbook_index.py)
    print(f"INDEX_DIR={index_output_dir}")


if __name__ == "__main__":
    main()
