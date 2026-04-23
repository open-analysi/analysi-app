#!/usr/bin/env python3
"""
Runbook matching and scoring algorithm.
Calculates confidence scores based on configurable criteria.
"""

import json
import re
from pathlib import Path
from typing import Any


class RunbookMatcher:
    """Match OCSF alerts to runbooks with confidence scoring."""

    # Configurable matching weights (can be adjusted over time)
    WEIGHTS = {
        "exact_detection_rule": 100,  # Exact match on detection rule
        "subcategory_match": 40,  # Same subcategory (primary matcher)
        "subcategory_similar": 25,  # Similar subcategory (same family)
        "alert_type_match": 20,  # Same alert_type (broad category)
        "source_category": 30,  # Same source category
        "mitre_overlap": 20,  # Per overlapping MITRE tactic
        "integration_compatibility": 15,  # Has required integrations
        "cve_same_vendor": 35,  # Same vendor for CVE attacks
        "cve_same_year": 10,  # Same year for CVEs
    }

    # Subcategory similarity groups (used for matching subcategories)
    SUBCATEGORY_SIMILARITY = {
        "injection": [
            "sql injection",
            "nosql injection",
            "ldap injection",
            "command injection",
            "code injection",
            "xpath injection",
            "xml injection",
        ],
        "xss": [
            "xss",
            "reflected xss",
            "stored xss",
            "dom xss",
            "cross site scripting",
        ],
        "authentication": [
            "brute force",
            "credential stuffing",
            "password spray",
            "authentication bypass",
            "authentication attack",
            "forced authentication",
        ],
        "file_inclusion": [
            "lfi",
            "rfi",
            "path traversal",
            "directory traversal",
            "local file inclusion",
            "remote file inclusion",
        ],
        "access_control": [
            "idor",
            "privilege escalation",
            "authorization bypass",
            "insecure direct object reference",
            "broken access control",
        ],
        "rce": ["rce", "remote code execution", "code execution"],
    }

    def __init__(self, index_dir: str = None):
        """Initialize with optional pre-built index directory."""
        self.index_dir = Path(index_dir) if index_dir else None
        self.runbooks_metadata = []
        if self.index_dir and (self.index_dir / "all_runbooks.json").exists():
            self.load_index()

    def load_index(self):
        """Load pre-built runbook index."""
        index_file = self.index_dir / "all_runbooks.json"
        with open(index_file) as f:
            data = json.load(f)
            # Handle both old format (list) and new format (with metadata)
            if isinstance(data, dict) and "runbooks" in data:
                self.runbooks_metadata = data["runbooks"]
            else:
                self.runbooks_metadata = data

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ""
        return text.lower().strip()

    def get_subcategory_family(self, subcategory: str) -> str:
        """Get the family for a subcategory."""
        normalized = self.normalize_text(subcategory)

        for family, types in self.SUBCATEGORY_SIMILARITY.items():
            if any(t in normalized or normalized in t for t in types):
                return family

        # Check for CVE
        if "cve-" in normalized:
            return "cve"

        return "other"

    def extract_cve_info(self, text: str) -> dict[str, str]:
        """Extract CVE year and vendor information."""
        info = {"year": None, "vendor": None}

        # Extract CVE year
        cve_match = re.search(r"CVE-(\d{4})-\d+", text, re.IGNORECASE)
        if cve_match:
            info["year"] = cve_match.group(1)

        # Extract vendor (simplified - could be enhanced)
        vendors = [
            "microsoft",
            "adobe",
            "cisco",
            "oracle",
            "apache",
            "atlassian",
            "vmware",
            "fortinet",
            "palo alto",
            "checkpoint",
        ]

        text_lower = text.lower()
        for vendor in vendors:
            if vendor in text_lower:
                info["vendor"] = vendor
                break

        return info

    def extract_ocsf_field(self, alert: dict[str, Any], field: str) -> Any:
        """
        Extract a field from an OCSF alert, with fallback to flat fields.
        This allows the scorer to work with both OCSF and legacy formats.
        """
        if field == "detection_rule":
            # OCSF: finding_info.analytic.name -> finding_info.title -> flat
            fi = alert.get("finding_info", {})
            return (
                fi.get("analytic", {}).get("name")
                or fi.get("title")
                or alert.get("detection_rule")
                or alert.get("rule_name")
                or ""
            )
        if field == "subcategory":
            # OCSF: second element in finding_info.types -> flat
            types = alert.get("finding_info", {}).get("types", [])
            if len(types) >= 2:
                return types[1]
            return alert.get("subcategory", "")
        if field == "alert_type":
            # OCSF: first element in finding_info.types -> flat
            types = alert.get("finding_info", {}).get("types", [])
            if types:
                return types[0]
            return alert.get("alert_type", "")
        if field == "source_category":
            # OCSF: metadata.labels with "source_category:" prefix -> flat
            for label in alert.get("metadata", {}).get("labels", []):
                if label.startswith("source_category:"):
                    return label.split(":", 1)[1]
            return alert.get("source_category", "")
        if field == "mitre_tactics":
            # OCSF: finding_info.attacks[].technique.uid -> flat
            attacks = alert.get("finding_info", {}).get("attacks", [])
            if attacks:
                ids = []
                for a in attacks:
                    tech = a.get("technique", {})
                    if tech.get("uid"):
                        ids.append(tech["uid"])
                return ids
            return alert.get("mitre_tactics", [])
        return ""

    def calculate_match_score(
        self, alert: dict[str, Any], runbook: dict[str, Any]
    ) -> tuple[float, dict[str, Any]]:
        """
        Calculate match score between an OCSF alert and runbook metadata.
        Alert can be OCSF Detection Finding or legacy flat format (auto-detected).
        Runbook metadata comes from YAML frontmatter (always flat fields).
        Returns (score, explanation_dict).
        """
        score = 0
        explanations = {"matched_criteria": [], "score_breakdown": {}}

        # 1. Exact detection rule match (highest priority)
        alert_rule = self.extract_ocsf_field(alert, "detection_rule").lower()
        runbook_rule = runbook.get("detection_rule", "").lower()

        if alert_rule and runbook_rule and alert_rule == runbook_rule:
            score += self.WEIGHTS["exact_detection_rule"]
            explanations["matched_criteria"].append("Exact detection rule match")
            explanations["score_breakdown"]["exact_detection_rule"] = self.WEIGHTS[
                "exact_detection_rule"
            ]

        # 2. Subcategory matching (primary attack classifier)
        alert_subcat = self.normalize_text(
            self.extract_ocsf_field(alert, "subcategory")
        )
        runbook_subcat = self.normalize_text(runbook.get("subcategory", ""))

        if alert_subcat and runbook_subcat:
            if alert_subcat == runbook_subcat:
                score += self.WEIGHTS["subcategory_match"]
                explanations["matched_criteria"].append(
                    f"Same subcategory: {alert_subcat}"
                )
                explanations["score_breakdown"]["subcategory_match"] = self.WEIGHTS[
                    "subcategory_match"
                ]
            elif self.get_subcategory_family(
                alert_subcat
            ) == self.get_subcategory_family(runbook_subcat):
                score += self.WEIGHTS["subcategory_similar"]
                family = self.get_subcategory_family(alert_subcat)
                explanations["matched_criteria"].append(
                    f"Similar subcategory family: {family}"
                )
                explanations["score_breakdown"]["subcategory_similar"] = self.WEIGHTS[
                    "subcategory_similar"
                ]

        # 3. Alert type matching (broad category like "Web Attack", "Brute Force")
        alert_type = self.normalize_text(self.extract_ocsf_field(alert, "alert_type"))
        runbook_type = self.normalize_text(runbook.get("alert_type", ""))

        if alert_type and runbook_type and alert_type == runbook_type:
            score += self.WEIGHTS["alert_type_match"]
            explanations["matched_criteria"].append(f"Same alert type: {alert_type}")
            explanations["score_breakdown"]["alert_type_match"] = self.WEIGHTS[
                "alert_type_match"
            ]

        # 4. Source category match
        alert_source = self.normalize_text(
            self.extract_ocsf_field(alert, "source_category")
        )
        runbook_source = runbook.get("source_category", "").lower()

        if alert_source and runbook_source and alert_source == runbook_source:
            score += self.WEIGHTS["source_category"]
            explanations["matched_criteria"].append(f"Same source: {alert_source}")
            explanations["score_breakdown"]["source_category"] = self.WEIGHTS[
                "source_category"
            ]

        # 5. MITRE technique overlap
        alert_mitre = set(self.extract_ocsf_field(alert, "mitre_tactics"))
        runbook_mitre = set(runbook.get("mitre_tactics", []))

        if alert_mitre and runbook_mitre:
            overlap = alert_mitre.intersection(runbook_mitre)
            if overlap:
                mitre_score = len(overlap) * self.WEIGHTS["mitre_overlap"]
                score += mitre_score
                explanations["matched_criteria"].append(
                    f"MITRE overlap: {', '.join(sorted(overlap))}"
                )
                explanations["score_breakdown"]["mitre_overlap"] = mitre_score

        # 6. CVE-specific matching
        alert_rule_text = self.extract_ocsf_field(alert, "detection_rule")
        alert_type_text = self.extract_ocsf_field(alert, "alert_type")
        alert_cve = self.extract_cve_info(alert_rule_text + " " + alert_type_text)
        runbook_cve = self.extract_cve_info(
            runbook.get("detection_rule", "") + " " + runbook.get("alert_type", "")
        )

        if alert_cve["vendor"] and runbook_cve["vendor"]:
            if alert_cve["vendor"] == runbook_cve["vendor"]:
                score += self.WEIGHTS["cve_same_vendor"]
                explanations["matched_criteria"].append(
                    f"Same vendor: {alert_cve['vendor']}"
                )
                explanations["score_breakdown"]["cve_same_vendor"] = self.WEIGHTS[
                    "cve_same_vendor"
                ]

        if alert_cve["year"] and runbook_cve["year"]:
            if alert_cve["year"] == runbook_cve["year"]:
                score += self.WEIGHTS["cve_same_year"]
                explanations["matched_criteria"].append(
                    f"Same CVE year: {alert_cve['year']}"
                )
                explanations["score_breakdown"]["cve_same_year"] = self.WEIGHTS[
                    "cve_same_year"
                ]

        return score, explanations

    def find_matches(
        self, alert: dict[str, Any], top_n: int = 5
    ) -> list[dict[str, Any]]:
        """
        Find best matching runbooks for an alert.
        Returns list of matches with scores and explanations.
        Note: Confidence interpretation should be done by LLM using confidence_rubric.md
        """
        matches = []

        for runbook in self.runbooks_metadata:
            score, explanation = self.calculate_match_score(alert, runbook)

            if score > 0:  # Only include runbooks with some match
                matches.append(
                    {"runbook": runbook, "score": score, "explanation": explanation}
                )

        # Sort by score descending
        matches.sort(key=lambda x: x["score"], reverse=True)

        return matches[:top_n]

    def get_match_scores(self) -> dict[str, int]:
        """Return the current scoring weights for reference."""
        return self.WEIGHTS


def main():
    """Example usage."""
    # Example OCSF Detection Finding alert
    example_alert = {
        "class_uid": 2004,
        "class_name": "Detection Finding",
        "severity_id": 4,
        "severity": "High",
        "activity_id": 1,
        "type_uid": 200401,
        "finding_info": {
            "title": "Potential NoSQL Injection Attack",
            "uid": "NOSQL-INJ-001",
            "types": ["Web Attack", "NoSQL Injection"],
            "analytic": {
                "name": "Potential NoSQL Injection Attack",
                "type_id": 1,
                "type": "Rule",
            },
            "attacks": [
                {
                    "technique": {
                        "uid": "T1190",
                        "name": "Exploit Public-Facing Application",
                    },
                    "tactic": {"uid": "TA0001", "name": "Initial Access"},
                }
            ],
        },
        "metadata": {
            "version": "1.3.0",
            "product": {"name": "WAF", "vendor_name": "Security"},
            "labels": ["source_category:WAF"],
        },
    }

    # Initialize matcher (would use actual index in practice)
    matcher = RunbookMatcher()

    # For demo, add some sample runbook metadata
    matcher.runbooks_metadata = [
        {
            "filename": "sql-injection-detection.md",
            "detection_rule": "Possible SQL Injection Payload Detected",
            "alert_type": "Web Attack",
            "subcategory": "SQL Injection",
            "source_category": "WAF",
            "mitre_tactics": ["T1190"],
        },
        {
            "filename": "xss-detection.md",
            "detection_rule": "Javascript Code Detected in Requested URL",
            "alert_type": "Web Attack",
            "subcategory": "XSS",
            "source_category": "WAF",
            "mitre_tactics": ["T1189", "T1059"],
        },
    ]

    # Find matches
    matches = matcher.find_matches(example_alert)

    print(f"Alert: {matcher.extract_ocsf_field(example_alert, 'detection_rule')}")
    print(
        f"Type: {matcher.extract_ocsf_field(example_alert, 'alert_type')} / {matcher.extract_ocsf_field(example_alert, 'subcategory')}\n"
    )

    for i, match in enumerate(matches, 1):
        print(f"{i}. {match['runbook']['filename']}")
        print(f"   Score: {match['score']}")
        print(f"   Matched: {', '.join(match['explanation']['matched_criteria'])}")
        print()


if __name__ == "__main__":
    main()
