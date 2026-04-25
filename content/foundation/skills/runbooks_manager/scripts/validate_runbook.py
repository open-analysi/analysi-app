#!/usr/bin/env python3
"""
Runbook Validation Script

Validates runbook.md files for:
- Correct YAML frontmatter (parsed without external dependencies)
- Required metadata fields
- Valid step structure (including sub-steps like 2a, 2b)
- WikiLink path resolution
- Token count estimation

No external dependencies required - uses built-in Python only.
"""

import re
import sys
from pathlib import Path


def parse_yaml_frontmatter(text: str) -> dict:
    """
    Parse simple YAML frontmatter using regex.
    Handles: scalar values, inline arrays [a, b], and multiline list arrays.
    Does NOT handle nested objects or literal block scalars (alert_examples).
    """
    metadata = {}

    # Handle single-line key: value pairs (must come before array parsing)
    for match in re.finditer(r"^(\w+):\s+(.+?)$", text, re.MULTILINE):
        key = match.group(1)
        value = match.group(2).strip()
        # Skip if this is an inline array (handled below)
        if value.startswith("["):
            continue
        # Remove quotes if present
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        metadata[key] = value

    # Handle inline arrays: key: [val1, val2]
    for match in re.finditer(r"^(\w+):\s*\[(.*?)\]", text, re.MULTILINE):
        key = match.group(1)
        values = match.group(2)
        items = [
            v.strip().strip('"').strip("'") for v in values.split(",") if v.strip()
        ]
        metadata[key] = items

    # Handle multiline list arrays:
    # key:
    #   - value1
    #   - value2
    current_key = None
    for line in text.split("\n"):
        key_match = re.match(r"^(\w+):\s*$", line)
        if key_match:
            current_key = key_match.group(1)
            # Don't overwrite if already parsed as inline array
            if current_key not in metadata or not isinstance(
                metadata[current_key], list
            ):
                metadata[current_key] = []
        elif current_key and re.match(r"^\s+-\s+(.+)", line):
            item_match = re.match(r"^\s+-\s+(.+)", line)
            if item_match:
                value = item_match.group(1).strip().strip('"').strip("'")
                if isinstance(metadata.get(current_key), list):
                    metadata[current_key].append(value)
        elif re.match(r"^[a-zA-Z]", line) and ":" in line:
            current_key = None

    return metadata


class RunbookValidator:
    """Validates runbook.md files against format specification."""

    # Required metadata fields (per format-specification.md)
    REQUIRED_METADATA = {
        "detection_rule",
        "alert_type",
        "source_category",
        "mitre_tactics",
        "integrations_required",
        "integrations_optional",
    }

    # Valid OCSF source categories
    VALID_SOURCE_CATEGORIES = {
        "WAF",
        "Web",
        "EDR",
        "Endpoint",
        "Identity",
        "Email",
        "Network",
        "Firewall",
        "Cloud",
        "Database",
        "Application",
    }

    # Valid patterns: 6 from format spec + 2 legacy (still used in templates/older runbooks)
    VALID_PATTERNS = {
        # Format spec patterns
        "hypothesis_formation",
        "evidence_correlation",
        "payload_analysis",
        "impact_assessment",
        "threat_synthesis",
        "integration_query",
        # Legacy patterns (used in templates and some runbooks)
        "llm_analysis",
        "llm_synthesis",
    }

    def __init__(self, skill_root: Path):
        """Initialize validator with skill root path (for resolving WikiLinks)."""
        self.skill_root = skill_root
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.included_files: set[str] = set()

    def validate_file(self, file_path: Path, is_sub_runbook: bool = False) -> bool:
        """Validate a single runbook file."""
        self.errors = []
        self.warnings = []
        self.included_files = set()

        if not file_path.exists():
            self.errors.append(f"File not found: {file_path}")
            return False

        content = file_path.read_text()

        if is_sub_runbook:
            return self._validate_sub_runbook(content, file_path)

        # Extract and validate frontmatter
        frontmatter, body = self._extract_frontmatter(content)
        if frontmatter is None:
            return False

        # Validate metadata
        self._validate_metadata(frontmatter)

        # Validate body structure
        self._validate_body(body, file_path)

        # Estimate token count (body only, excluding frontmatter)
        body_tokens = self._estimate_tokens(body)
        if body_tokens > 3000:
            self.warnings.append(
                f"Body token count (~{body_tokens}) is high; "
                f"consider extracting patterns to sub-runbooks"
            )

        return len(self.errors) == 0

    def _validate_sub_runbook(self, content: str, file_path: Path) -> bool:
        """Validate a sub-runbook fragment (no frontmatter required)."""
        if not content.strip():
            self.errors.append("Sub-runbook is empty")
            return False

        # Sub-runbooks should have at least one step or section header
        has_step = bool(re.search(r"^#{2,4}\s+", content, re.MULTILINE))
        if not has_step:
            self.warnings.append("Sub-runbook has no step or section headers")

        # Validate patterns if present
        for match in re.finditer(r"\*\*Pattern:\*\*\s*(\S+)", content):
            pattern = match.group(1)
            if pattern not in self.VALID_PATTERNS:
                self.errors.append(
                    f"Invalid pattern: '{pattern}'. "
                    f"Valid: {', '.join(sorted(self.VALID_PATTERNS))}"
                )

        # Check nested WikiLinks
        includes = re.findall(r"!\[\[([\w/._-]+\.md)\]\]", content)
        for include_path in includes:
            self._validate_include(include_path, file_path)

        # Token estimate for sub-runbooks (format spec: 100-300 tokens)
        tokens = self._estimate_tokens(content)
        if tokens > 500:
            self.warnings.append(
                f"Sub-runbook token count (~{tokens}) exceeds recommended 100-300"
            )

        return len(self.errors) == 0

    def _extract_frontmatter(self, content: str) -> tuple[dict | None, str]:
        """Extract YAML frontmatter and body."""
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
        if not match:
            self.errors.append("No YAML frontmatter found (missing --- delimiters)")
            return None, content

        yaml_text = match.group(1)
        body = match.group(2)

        metadata = parse_yaml_frontmatter(yaml_text)
        if not metadata:
            self.errors.append("YAML frontmatter is empty or could not be parsed")
            return None, content

        return metadata, body

    def _validate_metadata(self, metadata: dict):
        """Validate metadata fields."""
        # Check required fields
        for field in self.REQUIRED_METADATA:
            if field not in metadata:
                self.errors.append(f"Missing required field: {field}")

        # Validate source_category
        if "source_category" in metadata:
            if metadata["source_category"] not in self.VALID_SOURCE_CATEGORIES:
                self.warnings.append(
                    f"Uncommon source_category: '{metadata['source_category']}'. "
                    f"Known values: {', '.join(sorted(self.VALID_SOURCE_CATEGORIES))}"
                )

        # Validate MITRE tactics format
        if "mitre_tactics" in metadata:
            tactics = metadata["mitre_tactics"]
            if not isinstance(tactics, list):
                self.errors.append("mitre_tactics must be a list")
            else:
                for tactic in tactics:
                    if not re.match(r"^T\d{4}(\.\d{3})?$", str(tactic)):
                        self.warnings.append(
                            f"Non-standard MITRE tactic format: {tactic}"
                        )

        # Validate integrations are lists
        for field in ["integrations_required", "integrations_optional"]:
            if field in metadata and not isinstance(metadata[field], list):
                self.errors.append(f"{field} must be a list")

    def _validate_body(self, body: str, file_path: Path):
        """Validate runbook body structure."""
        # Check for critical steps marked with star
        if "★" not in body:
            self.warnings.append("No critical steps marked with ★")

        # Validate step structure: handles 1., 2a., 2b., 10. etc.
        steps = re.findall(
            r"(### \d+[a-z]?\..+?)(?=\n### \d|\n## |\Z)", body, re.DOTALL
        )

        if not steps:
            # Could be a sub-runbook (common/) with no step headers
            if "common/" not in str(file_path):
                self.errors.append(
                    "No investigation steps found (expected ### N. format)"
                )

        # Check for alert understanding and final analysis
        # These can be inline or via WikiLinks
        body_lower = body.lower()
        has_alert_understanding = (
            "alert understanding" in body_lower or "alert-understanding" in body_lower
        )
        has_final_analysis = (
            "final analysis" in body_lower or "final-analysis" in body_lower
        )

        if not has_alert_understanding:
            self.warnings.append(
                "Missing 'Alert Understanding' step or "
                "![[common/universal/alert-understanding.md]] include"
            )
        if not has_final_analysis:
            self.warnings.append(
                "Missing 'Final Analysis' step or "
                "![[common/universal/final-analysis-trio.md]] include"
            )

        # Validate patterns in steps
        for step in steps:
            pattern_match = re.search(r"\*\*Pattern:\*\*\s*(\S+)", step)
            if pattern_match:
                pattern = pattern_match.group(1)
                if pattern not in self.VALID_PATTERNS:
                    self.errors.append(
                        f"Invalid pattern: '{pattern}'. "
                        f"Valid: {', '.join(sorted(self.VALID_PATTERNS))}"
                    )

        # Validate WikiLink embeds: ![[path.md]]
        includes = re.findall(r"!\[\[([\w/._-]+\.md)\]\]", body)
        for include_path in includes:
            self._validate_include(include_path, file_path)

    def _validate_include(self, include_path: str, source_file: Path):
        """Validate WikiLink path exists and check for circular references."""
        if include_path in self.included_files:
            self.errors.append(f"Circular WikiLink reference: {include_path}")
            return

        self.included_files.add(include_path)

        # Resolve path relative to skill root
        full_path = self.skill_root / include_path
        if not full_path.exists():
            self.errors.append(f"WikiLink target not found: {include_path}")
        else:
            # Check nested includes for circular references
            included_content = full_path.read_text()
            nested_includes = re.findall(r"!\[\[([\w/._-]+\.md)\]\]", included_content)
            for nested in nested_includes:
                self._validate_include(nested, full_path)

    def _estimate_tokens(self, content: str) -> int:
        """Estimate token count (rough: ~4 characters per token)."""
        return len(content) // 4

    def print_report(self, file_label: str = ""):
        """Print validation report."""
        if file_label:
            print(f"  {file_label}")

        if self.errors:
            print("  ERRORS:")
            for error in self.errors:
                print(f"    - {error}")

        if self.warnings:
            print("  WARNINGS:")
            for warning in self.warnings:
                print(f"    - {warning}")

        if not self.errors and not self.warnings:
            print("  Passed (no errors or warnings)")


def find_skill_root(start_path: Path) -> Path:
    """
    Find the skill root directory by looking for common/ and repository/ dirs.
    Walks up from start_path until it finds a directory containing both.
    """
    current = start_path if start_path.is_dir() else start_path.parent

    for _ in range(10):  # safety limit
        if (current / "common").is_dir() and (current / "repository").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent

    # Fallback: return the starting directory (WikiLink validation will be unreliable)
    fallback = start_path if start_path.is_dir() else start_path.parent
    print(
        f"WARNING: Could not find skill root (no common/ + repository/ found).\n"
        f"  Falling back to: {fallback}\n"
        f"  WikiLink validation may produce false errors.\n"
        f"  Run from within the skill directory for accurate results.",
        file=sys.stderr,
    )
    return fallback


def validate_directory(
    directory: Path, skill_root: Path, is_sub_runbook: bool = False
) -> tuple[int, int]:
    """Validate all runbook .md files in a directory. Returns (passed, failed)."""
    validator = RunbookValidator(skill_root)
    md_files = sorted(directory.glob("*.md"))

    if not md_files:
        print("  (no .md files)")
        return 0, 0

    passed = 0
    failed = 0

    for file_path in md_files:
        relative = (
            file_path.relative_to(skill_root)
            if skill_root in file_path.parents
            else file_path.name
        )
        is_valid = validator.validate_file(file_path, is_sub_runbook=is_sub_runbook)

        if is_valid and not validator.warnings:
            print(f"  PASS  {relative}")
            passed += 1
        elif is_valid:
            print(f"  WARN  {relative}")
            validator.print_report()
            passed += 1  # warnings don't fail
        else:
            print(f"  FAIL  {relative}")
            validator.print_report()
            failed += 1

    return passed, failed


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python validate_runbook.py <runbook_file_or_directory>")
        print()
        print("Validates runbook .md files against the format specification.")
        print(
            "Automatically finds the skill root (containing common/ and repository/)."
        )
        print()
        print("Examples:")
        print("  python validate_runbook.py repository/sql-injection-detection.md")
        print("  python validate_runbook.py repository/")
        print("  python validate_runbook.py .")
        sys.exit(1)

    path = Path(sys.argv[1]).resolve()
    skill_root = find_skill_root(path)
    print(f"Skill root: {skill_root}\n")

    if path.is_file():
        # Validate single file
        validator = RunbookValidator(skill_root)
        relative = (
            path.relative_to(skill_root) if skill_root in path.parents else path.name
        )

        # Auto-detect sub-runbooks: files inside a common/ directory
        is_sub = "common/" in str(relative) or "/common/" in str(path)

        if validator.validate_file(path, is_sub_runbook=is_sub):
            label = " (sub-runbook)" if is_sub else ""
            print(f"PASS  {relative}{label}")
            if validator.warnings:
                validator.print_report()
        else:
            print(f"FAIL  {relative}")
            validator.print_report()
            sys.exit(1)
    else:
        # Validate directory (and subdirectories)
        total_passed = 0
        total_failed = 0

        # Check for repository/ and common/ subdirs
        dirs_to_check = []
        if (path / "repository").is_dir():
            dirs_to_check.append(("Repository", path / "repository", False))
        if (path / "common").is_dir():
            for subdir in sorted((path / "common").iterdir()):
                if subdir.is_dir():
                    md_files = list(subdir.glob("*.md"))
                    if md_files:
                        dirs_to_check.append((f"Common/{subdir.name}", subdir, True))

        # If no known subdirs, check the path itself
        if not dirs_to_check:
            dirs_to_check.append((path.name, path, False))

        for label, directory, is_sub in dirs_to_check:
            print(f"--- {label}{' (sub-runbooks)' if is_sub else ''} ---")
            p, f = validate_directory(directory, skill_root, is_sub_runbook=is_sub)
            total_passed += p
            total_failed += f
            print()

        # Summary
        total = total_passed + total_failed
        print("=" * 50)
        print(f"SUMMARY: {total_passed} passed, {total_failed} failed ({total} total)")

        if total_failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
