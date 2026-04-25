"""Knowledge Extraction pipeline node functions.

Each LLM node follows the factory pattern: make_*_node(llm) -> async closure.
Deterministic nodes are plain async functions.

Nodes use the SubStep executor for SkillsIR context + structured output.

Security: validate_output node includes suspicious content detection to block
dangerous patterns in agent-generated content (code injection, shell commands, etc.)
"""

import json
import re
from typing import Any

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from analysi.agentic_orchestration.content_policy import check_suspicious_content
from analysi.agentic_orchestration.langgraph.knowledge_extraction.prompts import (
    CLASSIFY_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    MERGE_PROMPT,
    PLACEMENT_PROMPT,
    RELEVANCE_PROMPT,
    SUMMARIZE_COMPLETED_PROMPT,
    SUMMARIZE_REJECTED_PROMPT,
    TRANSFORM_PROMPT,
    VALIDATE_LLM_PROMPT,
)
from analysi.agentic_orchestration.langgraph.substep import SubStep
from analysi.agentic_orchestration.langgraph.substep.definition import (
    ValidationResult,
)
from analysi.agentic_orchestration.langgraph.substep.executor import execute_substep
from analysi.config.logging import get_logger
from analysi.schemas.knowledge_extraction import (
    DocumentClassification,
    ExtractionSummary,
    MergeResult,
    PlacementDecision,
    RelevanceAssessment,
)
from analysi.schemas.knowledge_extraction import (
    ValidationResult as ValidationResultSchema,
)

logger = get_logger(__name__)


def _passthrough_validator(output: Any) -> ValidationResult:
    """Validator that always passes. Used when validation is handled elsewhere."""
    return ValidationResult(passed=True, errors=[])


# =============================================================================
# Node 1: classify_document (no SkillsIR)
# =============================================================================


def make_classify_node(llm):
    """Create classify_document node. No SkillsIR needed."""

    async def classify_node(state: dict) -> dict:
        substep = SubStep(
            name="classify_document",
            objective="Classify the document type for knowledge extraction",
            skills=[],
            task_prompt=CLASSIFY_PROMPT,
            validator=_passthrough_validator,
            needs_context=False,
            output_schema=DocumentClassification,
        )

        substep_state = {
            "content": _truncate(state["content"], 12000),
            "source_format": state["source_format"],
            "source_description": state["source_description"],
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=state["store"],
            llm=llm,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )

        classification = _parse_structured_output(result.output)
        return {"classification": classification}

    return classify_node


# =============================================================================
# Node 2: assess_relevance (SkillsIR: SKILL.md + tree)
# =============================================================================


def make_relevance_node(llm):
    """Create assess_relevance node. Uses SkillsIR for skill overview."""

    async def relevance_node(state: dict) -> dict:
        # Short-circuit: Node 1 already flagged as irrelevant
        classification = state.get("classification") or {}
        if classification.get("doc_type") == "low_security_runbook_relevance":
            return {
                "relevance": {
                    "is_relevant": False,
                    "applicable_namespaces": [],
                    "reasoning": classification.get(
                        "reasoning",
                        "Document classified as having low security runbook relevance.",
                    ),
                },
                "status": "rejected",
            }

        substep = SubStep(
            name="assess_relevance",
            objective="Determine if this document is relevant to the runbooks-manager skill. "
            "Load SKILL.md and the file tree to understand what the skill covers.",
            skills=["runbooks-manager"],
            task_prompt=RELEVANCE_PROMPT,
            validator=_passthrough_validator,
            needs_context=True,
            output_schema=RelevanceAssessment,
        )

        classification = state.get("classification") or {}
        substep_state = {
            "content": _truncate(state["content"], 10000),
            "classification": json.dumps(classification, default=str),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=state["store"],
            llm=llm,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )

        relevance = _parse_structured_output(result.output)

        # If not relevant, set status to rejected
        if relevance and not relevance.get("is_relevant", True):
            return {
                "relevance": relevance,
                "status": "rejected",
            }

        return {"relevance": relevance}

    return relevance_node


# =============================================================================
# Node 3: determine_placement (SkillsIR: tree + namespace samples)
# =============================================================================


def make_placement_node(llm):
    """Create determine_placement node. Uses SkillsIR for namespace context."""

    async def placement_node(state: dict) -> dict:
        relevance = state.get("relevance") or {}
        applicable_ns = relevance.get("applicable_namespaces", ["repository/"])

        substep = SubStep(
            name="determine_placement",
            objective=f"Determine where to place this document within the runbooks-manager skill. "
            f"Load the file tree and 1-2 files from candidate namespaces: {applicable_ns}",
            skills=["runbooks-manager"],
            task_prompt=PLACEMENT_PROMPT,
            validator=_passthrough_validator,
            needs_context=True,
            output_schema=PlacementDecision,
        )

        classification = state.get("classification") or {}
        substep_state = {
            "content": _truncate(state["content"], 8000),
            "classification": json.dumps(classification, default=str),
            "applicable_namespaces": json.dumps(applicable_ns, default=str),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=state["store"],
            llm=llm,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )

        placement = _parse_structured_output(result.output)
        return {"placement": placement}

    return placement_node


# =============================================================================
# Node 4a: extract_and_transform (create-new path)
# =============================================================================


def make_transform_node(llm):
    """Create extract_and_transform node. Uses SkillsIR for format exemplars."""

    async def transform_node(state: dict) -> dict:
        placement = state.get("placement") or {}
        target_ns = placement.get("target_namespace", "repository/")

        substep = SubStep(
            name="extract_and_transform",
            objective=f"Transform this document into the format used by the '{target_ns}' namespace "
            f"in runbooks-manager. Load format exemplars from that namespace and "
            f"references/building/format-specification.md.",
            skills=["runbooks-manager"],
            task_prompt=TRANSFORM_PROMPT,
            validator=_passthrough_validator,
            needs_context=True,
        )

        classification = state.get("classification") or {}
        substep_state = {
            "content": state["content"],
            "source_format": state["source_format"],
            "classification": json.dumps(classification, default=str),
            "target_namespace": target_ns,
            "target_filename": placement.get("target_filename", "extracted.md"),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=state["store"],
            llm=llm,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )

        return {"transformed_content": result.output}

    return transform_node


# =============================================================================
# Node 4b: merge_with_existing
# =============================================================================


def make_merge_node(llm):
    """Create merge_with_existing node. Uses SkillsIR for target + sibling files."""

    async def merge_node(state: dict) -> dict:
        placement = state.get("placement") or {}
        merge_target = placement.get("merge_target", "")

        # Load existing document content via store
        store = state["store"]
        existing_content = ""
        try:
            skill_name = state.get("skill_name", "runbooks-manager")
            existing_content = (
                await store.read_document_async(skill_name, merge_target) or ""
            )
        except Exception:
            logger.warning("could_not_load_merge_target", merge_target=merge_target)

        substep = SubStep(
            name="merge_with_existing",
            objective=f"Merge new knowledge into the existing file '{merge_target}' "
            f"in runbooks-manager. Load the target file and one sibling for style.",
            skills=["runbooks-manager"],
            task_prompt=MERGE_PROMPT,
            validator=_passthrough_validator,
            needs_context=True,
            output_schema=MergeResult,
        )

        classification = state.get("classification") or {}
        substep_state = {
            "content": state["content"],
            "classification": json.dumps(classification, default=str),
            "merge_target": merge_target,
            "existing_content": existing_content,
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=state["store"],
            llm=llm,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
        )

        merge_info = _parse_structured_output(result.output)

        # The transformed_content for merge is the merged_content
        merged_content = ""
        if merge_info:
            merged_content = merge_info.get("merged_content", "")
            # Ensure original_content is populated
            if not merge_info.get("original_content"):
                merge_info["original_content"] = existing_content

        return {
            "transformed_content": merged_content,
            "merge_info": merge_info,
        }

    return merge_node


# =============================================================================
# Node 5: validate_output (deterministic + LLM)
# =============================================================================


def make_validate_node(llm):
    """Create validate_output node. Deterministic checks + LLM coherence."""

    async def validate_node(state: dict) -> dict:
        content = state.get("transformed_content") or ""
        classification = state.get("classification") or {}
        placement = state.get("placement") or {}
        target_ns = placement.get("target_namespace", "repository/")
        doc_type = classification.get("doc_type", "")

        errors: list[str] = []
        warnings: list[str] = []

        # --- Deterministic checks ---
        if not content.strip():
            errors.append("Transformed content is empty")
        else:
            # Security check: Block suspicious patterns (code injection, shell commands)
            # This protects against malicious content in agent-generated documents
            suspicious_errors = check_suspicious_content(content)
            if suspicious_errors:
                errors.extend(suspicious_errors)

            if doc_type == "new_runbook" or target_ns.startswith("repository"):
                _validate_runbook(content, errors, warnings)
            elif target_ns.startswith("common/"):
                _validate_sub_runbook(content, errors, warnings)

            # WikiLink syntax check (all types)
            wikilinks = re.findall(r"!\[\[([^\]]+)\]\]", content)
            skill_tree = state.get("skill_tree") or []
            for link in wikilinks:
                if skill_tree and link not in skill_tree:
                    warnings.append(f"WikiLink target not in skill tree: {link}")

        # --- LLM coherence check (only if deterministic checks pass) ---
        if not errors and content.strip():
            try:
                llm_validation = await _run_llm_validation(
                    llm, content, classification, target_ns
                )
                if llm_validation:
                    if not llm_validation.get("valid", True):
                        errors.extend(llm_validation.get("errors", []))
                    warnings.extend(llm_validation.get("warnings", []))
            except Exception:
                logger.warning("LLM validation check failed, proceeding without it")

        validation = {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

        return {
            "validation": validation,
            "status": "completed",
        }

    return validate_node


def _validate_runbook(content: str, errors: list[str], warnings: list[str]) -> None:
    """Deterministic validation for runbooks (repository/)."""
    # Check YAML frontmatter
    if content.startswith("---"):
        fm_end = content.find("---", 3)
        if fm_end == -1:
            errors.append("YAML frontmatter not properly closed")
        else:
            try:
                fm_text = content[3:fm_end]
                fm = yaml.safe_load(fm_text)
                if fm:
                    required = [
                        "detection_rule",
                        "alert_type",
                        "subcategory",
                        "source_category",
                    ]
                    for field in required:
                        if field not in fm:
                            warnings.append(f"Missing frontmatter field: {field}")
            except yaml.YAMLError:
                errors.append("YAML frontmatter is malformed")
    else:
        warnings.append("No YAML frontmatter found (expected for repository/ runbooks)")

    # Check for critical step markers
    if "★" not in content:
        warnings.append("No critical step markers (★) found")

    # Token estimate (~4 chars per token)
    if len(content) > 4000:
        warnings.append("Content exceeds ~1000 tokens — consider trimming")


def _validate_sub_runbook(content: str, errors: list[str], warnings: list[str]) -> None:
    """Deterministic validation for sub-runbooks (common/)."""
    # Sub-runbooks should NOT have frontmatter
    if content.startswith("---"):
        warnings.append("Sub-runbooks typically don't have YAML frontmatter")

    # Should have at least one ### step header
    if "### " not in content:
        warnings.append("No ### step headers found (expected for sub-runbooks)")

    # Token estimate
    if len(content) > 1200:
        warnings.append("Content exceeds ~300 tokens — consider trimming")


async def _run_llm_validation(
    llm, content: str, classification: dict, target_ns: str
) -> dict | None:
    """Run LLM coherence check on transformed content."""
    prompt = VALIDATE_LLM_PROMPT.format(
        classification=json.dumps(classification, default=str),
        target_namespace=target_ns,
        transformed_content=_truncate(content, 8000),
    )

    structured_llm = llm.with_structured_output(ValidationResultSchema)
    response = await structured_llm.ainvoke(
        [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
    )

    if isinstance(response, BaseModel):
        return response.model_dump()
    return response


# =============================================================================
# Node 6: summarize_extraction
# =============================================================================


def make_summarize_node(llm):
    """Create summarize_extraction node. No SkillsIR needed — uses prior state."""

    async def summarize_node(state: dict) -> dict:
        status = state.get("status", "")
        classification = state.get("classification") or {}
        relevance = state.get("relevance") or {}
        placement = state.get("placement") or {}

        doc_type = classification.get("doc_type", "unknown")
        confidence = classification.get("confidence", "unknown")
        classification_reasoning = classification.get("reasoning", "")
        relevance_reasoning = relevance.get("reasoning", "")

        if status == "rejected":
            prompt_text = SUMMARIZE_REJECTED_PROMPT.format(
                doc_type=doc_type,
                confidence=confidence,
                classification_reasoning=classification_reasoning,
                relevance_reasoning=relevance_reasoning,
            )
        else:
            content = state.get("transformed_content") or state.get("content") or ""
            prompt_text = SUMMARIZE_COMPLETED_PROMPT.format(
                doc_type=doc_type,
                confidence=confidence,
                target_namespace=placement.get("target_namespace", ""),
                target_filename=placement.get("target_filename", ""),
                merge_strategy=placement.get("merge_strategy", "create_new"),
                classification_reasoning=classification_reasoning,
                relevance_reasoning=relevance_reasoning,
                content_preview=_truncate(content, 500),
            )

        try:
            structured_llm = llm.with_structured_output(ExtractionSummary)
            response = await structured_llm.ainvoke(
                [
                    SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
                    HumanMessage(content=prompt_text),
                ]
            )

            if isinstance(response, BaseModel):
                return {"extraction_summary": response.model_dump()["summary"]}
            if isinstance(response, dict):
                return {"extraction_summary": response.get("summary", "")}
            return {"extraction_summary": str(response)}
        except Exception:
            logger.warning("Summarize node failed, proceeding without summary")
            return {"extraction_summary": None}

    return summarize_node


# =============================================================================
# Helpers
# =============================================================================


def _parse_structured_output(output: str | dict | None) -> dict | None:
    """Parse SubStep output into dict. Handles JSON strings and dicts."""
    if output is None:
        return None
    if isinstance(output, dict):
        return output
    try:
        return json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding indicator if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... content truncated ...]"
