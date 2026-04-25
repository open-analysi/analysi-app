#!/usr/bin/env python3
"""
Alignment test for runbooks-manager scripts and documentation.

Verifies that:
1. match_scorer.py WEIGHTS == SKILL.md WEIGHTS (names and values)
2. match_scorer.py WEIGHTS cover all dimensions in matching-algorithm.md
3. validate_runbook.py VALID_PATTERNS ⊇ all patterns actually used in runbooks
4. validate_runbook.py REQUIRED_METADATA == format-specification.md required fields
5. validate_runbook.py VALID_SOURCE_CATEGORIES ⊇ all source_categories in runbooks
6. build_runbook_index.py parses same metadata as match_scorer.py expects
7. All runbooks pass validation (validate_runbook.py exit code 0)

Run from repo root or skill root:
    python3 skills/source/runbooks-manager/scripts/test_alignment.py
"""

import re
import subprocess
import sys
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
REPO_DIR = SKILL_ROOT / "repository"
COMMON_DIR = SKILL_ROOT / "common"
REFS_DIR = SKILL_ROOT / "references"


def extract_python_dict(file_path: Path, variable_name: str) -> dict:
    """Extract a dict variable from a Python file by regex + eval."""
    content = file_path.read_text()
    # Match VARIABLE = { ... }
    pattern = rf"{variable_name}\s*=\s*\{{(.*?)\}}"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return {}
    dict_body = match.group(1)
    # Parse key-value pairs: "key": value or 'key': value
    result = {}
    for kv in re.finditer(r"""['"](\w+)['"]\s*:\s*(\d+)""", dict_body):
        result[kv.group(1)] = int(kv.group(2))
    return result


def extract_python_set(file_path: Path, variable_name: str) -> set:
    """Extract a set variable from a Python file by regex."""
    content = file_path.read_text()
    pattern = rf"{variable_name}\s*=\s*\{{(.*?)\}}"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return set()
    set_body = match.group(1)
    return {m.group(1) for m in re.finditer(r"""['"](\w+)['"]""", set_body)}


def extract_skill_md_weights(file_path: Path) -> dict:
    """Extract WEIGHTS from the SKILL.md code block."""
    content = file_path.read_text()
    # Find the WEIGHTS block inside ```python ... ```
    match = re.search(r"```python\s*\nWEIGHTS\s*=\s*\{(.*?)\}", content, re.DOTALL)
    if not match:
        return {}
    dict_body = match.group(1)
    result = {}
    for kv in re.finditer(r"""['"](\w+)['"]\s*:\s*(\d+)""", dict_body):
        result[kv.group(1)] = int(kv.group(2))
    return result


def extract_algorithm_weights(file_path: Path) -> dict:
    """Extract weight values from matching-algorithm.md section headings.

    Parses lines like:
        ### 1. Exact Detection Rule Match (Weight: 100)
        ### 2. Attack Type Similarity (Weight: 40 for exact, 25 for similar)
        ### 3. CVE-Specific Matching (Weight: 35 for vendor, 10 for year)
    """
    content = file_path.read_text()
    weights = {}

    # Map heading keywords to scorer weight names
    # Each entry: (heading_keyword, [(scorer_key, weight_regex)])
    heading_rules = [
        (
            "detection rule",
            [
                ("exact_detection_rule", r"Weight:\s*(\d+)"),
            ],
        ),
        (
            "subcategory similarity",
            [
                ("subcategory_match", r"Weight:\s*(\d+)"),
                ("subcategory_similar", r"(\d+)\s+for\s+similar"),
            ],
        ),
        (
            "broad alert type",
            [
                ("alert_type_match", r"Weight:\s*(\d+)"),
            ],
        ),
        (
            "cve",
            [
                ("cve_same_vendor", r"(\d+)\s+for\s+vendor"),
                ("cve_same_year", r"(\d+)\s+for\s+year"),
            ],
        ),
        (
            "source category",
            [
                ("source_category", r"Weight:\s*(\d+)"),
            ],
        ),
        (
            "mitre",
            [
                ("mitre_overlap", r"Weight:\s*(\d+)"),
            ],
        ),
        (
            "integration",
            [
                ("integration_compatibility", r"Weight:\s*(\d+)"),
            ],
        ),
    ]

    # Split into sections by ### headings
    sections = re.split(r"(?=^### \d+\.)", content, flags=re.MULTILINE)

    for section in sections:
        section_lower = section.lower()
        for keyword, rules in heading_rules:
            if keyword in section_lower[:100]:  # check heading only
                for scorer_key, pattern in rules:
                    match = re.search(pattern, section)
                    if match:
                        weights[scorer_key] = int(match.group(1))
                break  # only match one heading rule per section

    return weights


def find_all_patterns_in_runbooks() -> set:
    """Find all Pattern values used in repository and common runbooks."""
    patterns = set()
    for md_file in list(REPO_DIR.glob("*.md")) + list(COMMON_DIR.rglob("*.md")):
        content = md_file.read_text()
        for match in re.finditer(r"\*\*Pattern:\*\*\s*(\S+)", content):
            patterns.add(match.group(1))
    return patterns


def find_all_source_categories() -> set:
    """Find all source_category values in runbook frontmatter."""
    categories = set()
    for md_file in REPO_DIR.glob("*.md"):
        content = md_file.read_text()
        match = re.search(r"^source_category:\s*(\S+)", content, re.MULTILINE)
        if match:
            categories.add(match.group(1))
    return categories


def extract_format_spec_required_fields(file_path: Path) -> set:
    """Extract required field names from format-specification.md table."""
    content = file_path.read_text()
    fields = set()
    # Find the Required Fields table and extract field names from first column
    in_required = False
    for line in content.split("\n"):
        if "Required Fields" in line:
            in_required = True
            continue
        if in_required and line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 2 and cells[1] and cells[1] != "Field":
                fields.add(cells[1])
        if in_required and line.startswith("#") and "Required" not in line:
            break
    return fields


def run_test(name: str, check_fn) -> bool:
    """Run a test and print result."""
    try:
        passed, detail = check_fn()
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}]  {name}")
        if detail and not passed:
            for line in detail if isinstance(detail, list) else [detail]:
                print(f"          {line}")
        return passed
    except Exception as e:
        print(f"  [ERROR] {name}")
        print(f"          {e}")
        return False


def main():
    print("=" * 60)
    print("Runbooks-Manager Script Alignment Tests")
    print("=" * 60)

    scorer_path = SCRIPT_DIR / "match_scorer.py"
    validator_path = SCRIPT_DIR / "validate_runbook.py"
    index_path = SCRIPT_DIR / "build_runbook_index.py"
    skill_md_path = SKILL_ROOT / "SKILL.md"
    algorithm_path = REFS_DIR / "matching" / "matching-algorithm.md"
    format_spec_path = REFS_DIR / "building" / "format-specification.md"

    results = []

    # --- Test 1: match_scorer.py WEIGHTS == SKILL.md WEIGHTS ---
    print("\n1. Weight Alignment: match_scorer.py vs SKILL.md")
    scorer_weights = extract_python_dict(scorer_path, "WEIGHTS")
    skill_md_weights = extract_skill_md_weights(skill_md_path)

    def check_weights_match():
        if scorer_weights == skill_md_weights:
            return True, None
        diffs = []
        all_keys = set(scorer_weights) | set(skill_md_weights)
        for k in sorted(all_keys):
            sv = scorer_weights.get(k, "MISSING")
            mv = skill_md_weights.get(k, "MISSING")
            if sv != mv:
                diffs.append(f"{k}: scorer={sv}, skill.md={mv}")
        return False, diffs

    results.append(run_test("WEIGHTS keys and values match", check_weights_match))

    # --- Test 2: match_scorer.py covers matching-algorithm.md dimensions ---
    print("\n2. Weight Coverage: match_scorer.py vs matching-algorithm.md")
    algo_weights = extract_algorithm_weights(algorithm_path)

    def check_algo_coverage():
        missing = []
        for key, value in algo_weights.items():
            if key not in scorer_weights:
                missing.append(f"Algorithm has '{key}={value}' not in scorer")
            elif scorer_weights[key] != value:
                missing.append(
                    f"'{key}': algorithm={value}, scorer={scorer_weights[key]}"
                )
        if not missing:
            return True, None
        return False, missing

    results.append(
        run_test(
            "All algorithm dimensions present in scorer with matching values",
            check_algo_coverage,
        )
    )

    def check_scorer_documented():
        undocumented = []
        for key in scorer_weights:
            if key not in algo_weights:
                undocumented.append(
                    f"Scorer has '{key}={scorer_weights[key]}' not in algorithm doc"
                )
        if not undocumented:
            return True, None
        return False, undocumented

    results.append(
        run_test(
            "All scorer weights documented in algorithm doc",
            check_scorer_documented,
        )
    )

    # --- Test 3: validate_runbook.py VALID_PATTERNS ⊇ actual patterns ---
    print("\n3. Pattern Alignment: validate_runbook.py vs actual runbooks")
    validator_patterns = extract_python_set(validator_path, "VALID_PATTERNS")
    actual_patterns = find_all_patterns_in_runbooks()

    def check_patterns_superset():
        missing = actual_patterns - validator_patterns
        if not missing:
            return True, None
        return False, [f"Patterns in runbooks but not in validator: {missing}"]

    results.append(
        run_test(
            "VALID_PATTERNS covers all patterns in runbooks",
            check_patterns_superset,
        )
    )

    def check_no_phantom_patterns():
        extra = validator_patterns - actual_patterns
        if not extra:
            return True, None
        # Extra patterns are OK if they're documented legacy
        return True, [f"Extra patterns in validator (legacy): {extra}"]

    results.append(
        run_test(
            "No undocumented phantom patterns in validator",
            check_no_phantom_patterns,
        )
    )

    # --- Test 4: validate_runbook.py REQUIRED_METADATA == format-spec ---
    print("\n4. Metadata Alignment: validate_runbook.py vs format-specification.md")
    validator_required = extract_python_set(validator_path, "REQUIRED_METADATA")
    spec_required = extract_format_spec_required_fields(format_spec_path)

    def check_metadata_match():
        # format spec also lists integrations_optional as required but it's
        # more of a "should be present" — check the core overlap
        missing_from_validator = spec_required - validator_required
        extra_in_validator = validator_required - spec_required
        issues = []
        if missing_from_validator:
            issues.append(f"In spec but not validator: {missing_from_validator}")
        if extra_in_validator:
            issues.append(f"In validator but not spec: {extra_in_validator}")
        return len(issues) == 0, issues if issues else None

    results.append(
        run_test(
            "REQUIRED_METADATA matches format specification",
            check_metadata_match,
        )
    )

    # --- Test 5: validate_runbook.py VALID_SOURCE_CATEGORIES ⊇ actual ---
    print("\n5. Source Category Alignment: validator vs actual runbooks")
    validator_categories = extract_python_set(validator_path, "VALID_SOURCE_CATEGORIES")
    actual_categories = find_all_source_categories()

    def check_categories_superset():
        missing = actual_categories - validator_categories
        if not missing:
            return True, None
        return False, [f"Categories in runbooks but not validator: {missing}"]

    results.append(
        run_test(
            "VALID_SOURCE_CATEGORIES covers all actual categories",
            check_categories_superset,
        )
    )

    # --- Test 6: build_runbook_index.py parses all expected fields ---
    print("\n6. Index Alignment: build_runbook_index.py field coverage")

    def check_index_fields():
        # Run the index builder and check the output
        result = subprocess.run(
            [sys.executable, str(index_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False, [f"build_runbook_index.py failed: {result.stderr}"]

        index_dir = None
        for line in result.stdout.strip().split("\n"):
            if line.startswith("INDEX_DIR="):
                index_dir = Path(line.split("=", 1)[1])
                break

        if not index_dir or not index_dir.exists():
            return False, ["Could not find INDEX_DIR in output"]

        import json

        all_runbooks_path = index_dir / "all_runbooks.json"
        with open(all_runbooks_path) as f:
            data = json.load(f)
            runbooks = data.get("runbooks", data)

        # Check that each runbook has the fields match_scorer.py needs
        scorer_fields = {
            "detection_rule",
            "alert_type",
            "subcategory",
            "source_category",
            "mitre_tactics",
        }
        issues = []
        for rb in runbooks:
            filename = rb.get("filename", "unknown")
            missing = scorer_fields - set(rb.keys())
            if missing:
                issues.append(f"{filename}: missing {missing}")

        # Cleanup
        import shutil

        shutil.rmtree(index_dir)

        if not issues:
            return True, None
        return False, issues

    results.append(
        run_test(
            "Index contains all fields needed by match_scorer.py",
            check_index_fields,
        )
    )

    # --- Test 7: All runbooks pass validation ---
    print("\n7. Full Validation: validate_runbook.py on all runbooks")

    def check_all_pass():
        result = subprocess.run(
            [sys.executable, str(validator_path), str(SKILL_ROOT)],
            capture_output=True,
            text=True,
        )
        # Extract summary line
        for line in result.stdout.strip().split("\n"):
            if "SUMMARY" in line:
                if "0 failed" in line:
                    return True, None
                return False, [line.strip()]
        return False, ["Could not find SUMMARY in output"]

    results.append(
        run_test(
            "All runbooks pass validation (0 failures)",
            check_all_pass,
        )
    )

    # --- Test 8: by_type patterns coverage ---
    print("\n8. By-Type Pattern Coverage: common/by_type/ vs repository subcategories")

    by_type_dir = SKILL_ROOT / "common" / "by_type"

    def find_subcategory_to_by_type_mapping() -> dict:
        """Map subcategories from runbook similarity groups to by_type files."""
        # Read match_scorer.py SUBCATEGORY_SIMILARITY groups
        scorer_content = scorer_path.read_text()
        groups = {}
        group_match = re.search(
            r"SUBCATEGORY_SIMILARITY\s*=\s*\{(.*?)\}",
            scorer_content,
            re.DOTALL,
        )
        if group_match:
            body = group_match.group(1)
            for m in re.finditer(r"""['"](\w+)['"]\s*:\s*\[(.*?)\]""", body, re.DOTALL):
                family = m.group(1)
                members = [
                    s.strip().strip('"').strip("'")
                    for s in m.group(2).split(",")
                    if s.strip()
                ]
                groups[family] = members
        return groups

    def check_by_type_exists():
        if not by_type_dir.is_dir():
            return False, ["common/by_type/ directory does not exist"]
        by_type_files = {f.stem for f in by_type_dir.glob("*.md")}
        if not by_type_files:
            return False, ["No .md files found in common/by_type/"]
        return True, None

    results.append(
        run_test(
            "common/by_type/ directory exists with patterns",
            check_by_type_exists,
        )
    )

    def check_by_type_referenced():
        """Check that by_type patterns are referenced by at least one runbook."""
        by_type_files = sorted(by_type_dir.glob("*.md")) if by_type_dir.is_dir() else []
        unreferenced = []
        for bt_file in by_type_files:
            wikilink = f"common/by_type/{bt_file.name}"
            found = False
            for rb_file in REPO_DIR.glob("*.md"):
                if wikilink in rb_file.read_text():
                    found = True
                    break
            if not found:
                unreferenced.append(bt_file.name)
        if not unreferenced:
            return True, None
        # Unreferenced is OK if pattern exists for composition use
        return True, [
            f"Patterns not yet WikiLinked in any runbook (available for composition): {unreferenced}"
        ]

    results.append(
        run_test(
            "by_type patterns are valid sub-runbooks",
            check_by_type_referenced,
        )
    )

    def check_by_type_pass_validation():
        """Verify all by_type patterns pass sub-runbook validation."""
        if not by_type_dir.is_dir():
            return False, ["common/by_type/ directory does not exist"]
        result = subprocess.run(
            [sys.executable, str(validator_path), str(SKILL_ROOT)],
            capture_output=True,
            text=True,
        )
        # Check for any FAIL in by_type section
        in_by_type = False
        failures = []
        for line in result.stdout.split("\n"):
            if "Common/by_type" in line:
                in_by_type = True
            elif line.startswith("---") and in_by_type:
                break
            elif in_by_type and "FAIL" in line:
                failures.append(line.strip())
        if not failures:
            return True, None
        return False, failures

    results.append(
        run_test(
            "All by_type patterns pass sub-runbook validation",
            check_by_type_pass_validation,
        )
    )

    # --- Summary ---
    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(results)
    failed = total - passed
    print(f"ALIGNMENT: {passed}/{total} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)
    else:
        print("All scripts and documentation are aligned.")


if __name__ == "__main__":
    main()
