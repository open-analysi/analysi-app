"""Runbook Matching validators.

Validators for scoring, confidence, and runbook output.
"""

import json
import re

from analysi.agentic_orchestration.langgraph.substep.definition import (
    ValidationResult,
)

# Valid confidence levels
VALID_CONFIDENCE_LEVELS = {"very_high", "high", "medium", "low", "very_low"}


def _extract_json_from_output(output: str) -> str:
    """Extract JSON from LLM output, handling markdown code blocks.

    LLMs often wrap JSON in markdown code blocks like:
    ```json
    {"key": "value"}
    ```

    This function extracts the raw JSON for parsing.
    """
    output = output.strip()

    # Try to extract from markdown code block (```json ... ``` or ``` ... ```)
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    match = re.search(code_block_pattern, output)
    if match:
        return match.group(1).strip()

    # If no code block, return as-is (might be raw JSON)
    return output


# Valid composition strategies
VALID_STRATEGIES = {
    "same_attack_family_adaptation",
    "multi_source_blending",
    "category_based_assembly",
    "minimal_scaffold",
}


def validate_matches(output: str) -> ValidationResult:
    """Validate scoring output has proper match format.

    Expected JSON format:
    {
        "matches": [
            {"runbook": {...}, "score": 150, "explanation": {...}},
            ...
        ],
        "top_score": 150,
        "has_exact_rule": true
    }
    """
    try:
        json_str = _extract_json_from_output(output)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return ValidationResult(passed=False, errors=[f"Invalid JSON: {e}"])

    errors = []

    # Check required fields
    if "matches" not in data:
        errors.append("Missing 'matches' field")
    elif not isinstance(data["matches"], list):
        errors.append("'matches' must be a list")
    elif len(data["matches"]) == 0:
        errors.append("'matches' is empty - no matches found")
    else:
        # Validate each match entry
        for i, match in enumerate(data["matches"]):
            if "score" not in match:
                errors.append(f"Match {i}: missing 'score' field")
            if "runbook" not in match:
                errors.append(f"Match {i}: missing 'runbook' field")

    if "top_score" not in data:
        errors.append("Missing 'top_score' field")

    if "has_exact_rule" not in data:
        errors.append("Missing 'has_exact_rule' field")

    return ValidationResult(passed=len(errors) == 0, errors=errors)


def validate_confidence(output: str) -> ValidationResult:
    """Validate confidence determination output.

    Expected JSON format:
    {
        "confidence": "high",
        "score": 150,
        "path": "match"
    }
    """
    try:
        json_str = _extract_json_from_output(output)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return ValidationResult(passed=False, errors=[f"Invalid JSON: {e}"])

    errors = []

    # Check required fields
    if "confidence" not in data:
        errors.append("Missing 'confidence' field")
    elif data["confidence"] not in VALID_CONFIDENCE_LEVELS:
        errors.append(f"Invalid confidence level: {data['confidence']}")

    if "score" not in data:
        errors.append("Missing 'score' field")

    if "path" not in data:
        errors.append("Missing 'path' field")

    return ValidationResult(passed=len(errors) == 0, errors=errors)


def _validate_markdown_hierarchy(content: str) -> list[str]:
    """Validate markdown heading hierarchy.

    Checks:
    - Document starts with H1
    - No heading level skipping (H1 → H3 is invalid)
    - Has a Steps section
    """
    errors = []

    # Extract headings: (hashes, text)
    headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)

    if not headings:
        return ["No headings found in runbook"]

    # Check first heading is H1
    if len(headings[0][0]) != 1:
        errors.append(f"Document should start with H1, found H{len(headings[0][0])}")

    # Check no level skipping (H1 → H3 is bad, H1 → H2 → H3 is good)
    prev_level = 0
    for hashes, text in headings:
        level = len(hashes)
        if level > prev_level + 1 and prev_level > 0:
            errors.append(
                f"Heading level skipped: H{prev_level} to H{level} ('{text.strip()}')"
            )
        prev_level = level

    # Check required sections exist
    heading_texts = [h[1].lower().strip() for h in headings]
    if not any("step" in h for h in heading_texts):
        errors.append("Missing 'Steps' section")

    return errors


def validate_runbook_output(output: str) -> ValidationResult:
    """Validate composed runbook output.

    Composed runbooks are for immediate use (not storage), so they should:
    - Have ★ critical step markers
    - Be self-contained (no @include, no WikiLinks)
    - NOT have YAML frontmatter (that's for stored runbooks only)
    - Have valid markdown hierarchy
    """
    if not output or not output.strip():
        return ValidationResult(passed=False, errors=["Runbook is empty"])

    errors = []

    # Check for critical step markers
    if "★" not in output:
        errors.append("Missing critical step markers (★)")

    # Check for @include directives (should be resolved)
    if "@include" in output:
        errors.append("Contains unresolved @include directives")

    # Check for WikiLinks (should be expanded)
    if re.search(r"!\[\[.+?\]\]", output):
        errors.append("Contains unresolved WikiLinks (![[...]])")

    # Check for YAML frontmatter (composed runbooks should NOT have it)
    if output.strip().startswith("---"):
        errors.append("Composed runbook should not have YAML frontmatter")

    # Validate markdown hierarchy
    hierarchy_errors = _validate_markdown_hierarchy(output)
    errors.extend(hierarchy_errors)

    return ValidationResult(passed=len(errors) == 0, errors=errors)


def validate_matched_runbook(output: str) -> ValidationResult:
    """Validate a matched (fetched) runbook from the repository.

    Matched runbooks are stored runbooks that may have YAML frontmatter.
    They should still be self-contained (WikiLinks expanded).
    Unlike composed runbooks, frontmatter is expected and allowed.
    """
    if not output or not output.strip():
        return ValidationResult(passed=False, errors=["Runbook is empty"])

    errors = []

    # Check for unresolved WikiLinks (should be expanded by fetch)
    if re.search(r"!\[\[.+?\]\]", output):
        errors.append("Contains unresolved WikiLinks (![[...]])")

    # Check for @include directives
    if "@include" in output:
        errors.append("Contains unresolved @include directives")

    return ValidationResult(passed=len(errors) == 0, errors=errors)


def validate_gap_analysis(output: str) -> ValidationResult:
    """Validate gap analysis output from composition step.

    Expected JSON format:
    {
        "gaps": [
            {"category": "...", "description": "...", "severity": "high"},
            ...
        ],
        "coverage_assessment": "..."
    }
    """
    try:
        json_str = _extract_json_from_output(output)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return ValidationResult(passed=False, errors=[f"Invalid JSON: {e}"])

    errors = []

    # Check required fields
    if "gaps" not in data:
        errors.append("Missing 'gaps' field")
    elif not isinstance(data["gaps"], list):
        errors.append("'gaps' must be a list")

    if "coverage_assessment" not in data:
        errors.append("Missing 'coverage_assessment' field")

    return ValidationResult(passed=len(errors) == 0, errors=errors)


def validate_strategy(output: str) -> ValidationResult:
    """Validate strategy selection output.

    Expected JSON format:
    {
        "strategy": "multi_source_blending",
        "sources": [
            {"runbook": "...", "sections": ["..."], "reason": "..."},
            ...
        ],
        "template": "..."
    }
    """
    try:
        json_str = _extract_json_from_output(output)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return ValidationResult(passed=False, errors=[f"Invalid JSON: {e}"])

    errors = []

    # Check required fields
    if "strategy" not in data:
        errors.append("Missing 'strategy' field")
    elif data["strategy"] not in VALID_STRATEGIES:
        errors.append(f"Invalid strategy: {data['strategy']}")

    if "sources" not in data:
        errors.append("Missing 'sources' field")
    elif not isinstance(data["sources"], list):
        errors.append("'sources' must be a list")

    # template can be null/None, so just check it exists
    if "template" not in data:
        errors.append("Missing 'template' field")

    return ValidationResult(passed=len(errors) == 0, errors=errors)


def validate_extraction(output: str) -> ValidationResult:
    """Validate extraction output with provenance.

    Expected JSON format:
    {
        "extractions": [
            {"content": "...", "source": "...", "section": "..."},
            ...
        ],
        "remaining_gaps": ["..."]
    }
    """
    try:
        json_str = _extract_json_from_output(output)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return ValidationResult(passed=False, errors=[f"Invalid JSON: {e}"])

    errors = []

    # Check required fields
    if "extractions" not in data:
        errors.append("Missing 'extractions' field")
    elif not isinstance(data["extractions"], list):
        errors.append("'extractions' must be a list")
    else:
        # Validate each extraction has provenance
        for i, extraction in enumerate(data["extractions"]):
            if "source" not in extraction:
                errors.append(f"Extraction {i}: missing 'source' field (provenance)")
            if "content" not in extraction:
                errors.append(f"Extraction {i}: missing 'content' field")

    if "remaining_gaps" not in data:
        errors.append("Missing 'remaining_gaps' field")
    elif not isinstance(data["remaining_gaps"], list):
        errors.append("'remaining_gaps' must be a list")

    return ValidationResult(passed=len(errors) == 0, errors=errors)
