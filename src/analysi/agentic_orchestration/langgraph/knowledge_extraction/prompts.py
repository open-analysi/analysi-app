"""Prompt templates for Knowledge Extraction pipeline nodes.

Each prompt is a format string that receives state variables via {placeholders}.
SkillsIR context is injected via {context} when the node uses needs_context=True.
"""

# =============================================================================
# System Prompt
# =============================================================================

EXTRACTION_SYSTEM_PROMPT = (
    "You are an expert knowledge engineer specializing in cybersecurity investigation "
    "runbooks. Your task is to analyze, classify, and transform security documents into "
    "structured knowledge that can be added to a skill's knowledge base. You follow "
    "established conventions precisely and never fabricate technical content."
)

# =============================================================================
# Node 1: classify_document
# =============================================================================

CLASSIFY_PROMPT = """Classify the following security document into one of the predefined knowledge types.

## Document
Source format: {source_format}
Description: {source_description}

Content:
{content}

## Classification Guide

| doc_type | What it looks like | Target namespace |
|----------|-------------------|-----------------|
| new_runbook | Full investigation procedure, SOAR playbook, step-by-step triage guide | repository/ |
| source_evidence_pattern | How to collect/analyze evidence from a specific source (WAF, EDR, SIEM) | common/by_source/ |
| attack_type_pattern | Base investigation pattern for an attack family (brute force, phishing) | common/by_type/ |
| evidence_collection | Generic evidence collection technique (threat intel, network capture) | common/evidence/ |
| universal_pattern | Pattern applicable to all investigations (alert understanding, final analysis) | common/universal/ |
| reference_documentation | Guidance docs, scoring algorithms, format specs | references/ |
| low_security_runbook_relevance | Content unrelated to security investigations: HR policies, marketing, recipes, generic tutorials, meeting notes, or documents too thin to extract meaningful knowledge from | (none — document will be rejected) |

Classify the document based on its content characteristics. Consider the structure, \
scope, and purpose of the document when making your determination. If the document \
has no meaningful connection to security investigation procedures, classify it as \
low_security_runbook_relevance."""

# =============================================================================
# Node 2: assess_relevance
# =============================================================================

RELEVANCE_PROMPT = """Assess whether this document contains knowledge useful for the target skill.

## Document
Classification: {classification}

Content:
{content}

## Skill Context
{context}

## Assessment Criteria
- Does this document cover security investigation knowledge?
- Would it be useful for building or improving runbooks?
- Does it overlap with existing content? (overlap is OK if it adds new perspective)
- Which namespaces in the skill could benefit from this content?

If the document is NOT relevant to security investigations (e.g., HR policies, \
marketing material, unrelated technical docs), mark it as not relevant."""

# =============================================================================
# Node 3: determine_placement
# =============================================================================

PLACEMENT_PROMPT = """Determine where this document should be placed within the skill.

## Document
Classification: {classification}
Applicable namespaces: {applicable_namespaces}

Content:
{content}

## Skill Context
{context}

## Decisions to Make
1. **Target namespace**: Which namespace best fits this content?
2. **Target filename**: Following the naming conventions below
3. **Merge strategy**: Create a new file or merge with an existing one?

## Naming Rules
- repository/: {{detection-rule-slug}}.md (kebab-case, descriptive)
- common/by_source/: {{source}}-{{pattern-name}}.md (e.g., edr-process-evidence.md)
- common/by_type/: {{attack-type}}-base.md (e.g., brute-force-base.md)
- common/evidence/: {{technique-name}}.md (e.g., network-traffic-analysis.md)
- references/: {{topic}}/{{document-name}}.md

## Merge Strategy
- **create_new**: No existing document covers this topic, or the input is different enough
- **merge_with_existing**: An existing document covers the same topic and the input adds \
complementary knowledge. Set merge_target to the existing file path."""

# =============================================================================
# Node 4a: extract_and_transform (create-new path)
# =============================================================================

TRANSFORM_PROMPT = """Transform the input document into markdown matching the target namespace's format.

## Input Document
Source format: {source_format}
Classification: {classification}
Target namespace: {target_namespace}
Target filename: {target_filename}

Content:
{content}

## Format Context
{context}

## Transformation Guidelines

### Strip vs Keep Framework
| Category | Action |
|----------|--------|
| Specific IPs, domains, hashes | STRIP — replace with symbolic placeholders |
| Specific tool names / vendor UIs | STRIP — replace with generic integration category |
| Ticket IDs, case numbers, analyst names | STRIP — remove entirely |
| Investigation procedures and decision logic | KEEP — this is the core knowledge |
| Integration categories (SIEM, EDR, TI) | KEEP — use generic category names |
| Thresholds, timeframes, severity logic | KEEP — these encode expert judgment |
| Data flow between steps | KEEP — use alert.*, outputs.*, params.* conventions |

### One-Case-to-General-Pattern
Extract the investigation methodology, not the specific case narrative. \
Convert case-specific findings into conditional decision branches.

### Query Fabrication Guard
NEVER invent queries or commands not present in the source document. \
Use generic integration category form: "Query [SIEM/EDR/TI] for [what]".

### Output Requirements
Your output must follow the same markdown structure as the format context examples. \
The output must be indistinguishable from a hand-written document already in the skill.

Output ONLY the transformed markdown content. No explanations or wrappers."""

# =============================================================================
# Node 4b: merge_with_existing
# =============================================================================

MERGE_PROMPT = """Merge new knowledge from the input document into the existing skill document.

## Input Document (new knowledge to merge)
Classification: {classification}

Content:
{content}

## Existing Document (to merge into)
Path: {merge_target}

{existing_content}

## Style Context
{context}

## Merge Principles
- PRESERVE existing structure — add to existing sections rather than reorganizing
- New knowledge is ADDITIVE — existing steps and patterns are preserved
- If the input contradicts existing content, add as an alternative perspective
- Update YAML frontmatter (if present) to reflect new coverage
- NO deletions — merge only adds or augments

Produce the complete merged document content."""

# =============================================================================
# Node 5: validate_output (LLM coherence check)
# =============================================================================

# =============================================================================
# Node 6: summarize_extraction
# =============================================================================

SUMMARIZE_COMPLETED_PROMPT = """Write a 2-3 sentence human-readable summary of this knowledge extraction.

## Extraction Details
- Document type: {doc_type}
- Confidence: {confidence}
- Relevant: yes
- Target location: {target_namespace}{target_filename}
- Action: {merge_strategy}

## Classification reasoning
{classification_reasoning}

## Relevance reasoning
{relevance_reasoning}

## Content preview (first 500 chars)
{content_preview}

## Instructions
Explain in plain language:
1. What knowledge was extracted from the source document
2. Why it's relevant to the skill
3. What will happen when applied (new file created or existing file updated)

Write for a security analyst reviewing this extraction. Do NOT mention internal implementation details like node names, pipeline stages, or technical infrastructure."""

SUMMARIZE_REJECTED_PROMPT = """Write a 2-3 sentence explanation of why this document was rejected.

## Document Classification
- Type: {doc_type}
- Confidence: {confidence}

## Classification reasoning
{classification_reasoning}

## Relevance Assessment
- Relevant: no
- Reasoning: {relevance_reasoning}

## Instructions
Explain in plain language why this document is not suitable for the security investigation skill.
Write for a security analyst. Do NOT mention internal implementation details like node names, pipeline stages, or technical infrastructure."""

# =============================================================================
# Node 5: validate_output (LLM coherence check)
# =============================================================================

VALIDATE_LLM_PROMPT = """Check the following transformed document for quality issues.

## Document
Classification: {classification}
Target namespace: {target_namespace}

Content:
{transformed_content}

## Quality Checks
1. Is the content technically coherent for a security investigation context?
2. Are there any hallucinated tool names or integration references?
3. Is the style consistent with established skill conventions?
4. Are investigation steps logically ordered?

Return your assessment. Mark as valid if no significant issues found. \
Warnings are acceptable for minor style suggestions."""
