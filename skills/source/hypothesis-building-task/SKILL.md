---
name: hypothesis-building-task
description: Build hypothesis generation tasks for security investigation workflows. Use when creating tasks that form investigation hypotheses from runbooks. These tasks combine static hypotheses (baked in at Kea-time) with dynamic LLM augmentation (at runtime).
---

# Hypothesis Building Task Skill

## Overview

Hypothesis generation tasks bridge runbook knowledge with per-alert analysis. Unlike reusable tasks, these are created NEW for each workflow during Kea workflow generation.

**Key Architecture:**
```
Kea (once per rule) → Creates workflow with hypothesis task
                      Static hypotheses baked in from runbook

Workflow (1000s of runs) → Each run, LLM can add alert-specific hypotheses
```

## Purpose: The Investigation Charter

The hypothesis task serves as the **table of contents** for the investigation. It declares upfront: "Here are the questions we're trying to answer."

**Why this matters:**

1. **Grounds the investigation** - Instead of blindly gathering enrichments, each task has a purpose
2. **Enables structured disposition** - The final analysis can reason: "We asked H1, H2, H3. Here's what we found for each."
3. **Creates narrative arc** - The investigation has a beginning (hypotheses), middle (evidence gathering), and end (conclusions)

**Data Flow (Implicit Mapping):**
```
Hypothesis Task → outputs investigation_hypotheses [H1, H2, H3, H4]
                          ↓
Investigation Tasks → gather evidence independently
                          ↓
Disposition Task → maps enrichments to hypotheses, draws conclusions
```

The hypothesis task doesn't dictate which tasks answer which hypotheses. That mapping happens implicitly at disposition time, where the LLM synthesizes all evidence against all hypotheses.

## When to Use This Skill

**Use when:**
- Phase 2 proposes a hypothesis generation task (designation: `new`)
- Runbook has `pattern: hypothesis_formation` or outputs `investigation_hypotheses`
- Building a task that forms investigation theories for an alert type

**Key Characteristics:**
- Created NEW for each workflow (not reusable across workflows)
- Contain static hypotheses from runbook (baked in at Kea-time)
- Allow dynamic LLM augmentation (at workflow runtime)

## Hypothesis JSON Schema

Each hypothesis object MUST follow this schema:

```json
{
  "id": "string (H1, H2, etc.)",
  "question": "string (yes/no investigative question)",
  "validates": "string (what this hypothesis helps determine)",
  "evidence_sources": ["string (which tasks/enrichments provide evidence)"]
}
```

**Example:**
```json
{
  "id": "H2",
  "question": "Did PowerShell successfully execute on the Exchange server?",
  "validates": "CVE-2022-41082 RCE exploitation success",
  "evidence_sources": ["edr_exchange_server_verification", "splunk_http_response_pattern_analysis"]
}
```

## Extracting Hypotheses from Runbooks

Look for these patterns in runbook steps:
- `pattern: hypothesis_formation`
- `outputs: investigation_hypotheses`
- Steps titled "Alert Understanding", "Initial Assessment", or similar
- Decision points that frame the investigation

Extract key investigative questions from:
- "Purpose: Validates X vs Y" statements
- "Decision Points" sections
- Step focus areas

**Example extraction from ProxyNotShell runbook:**
```
Step 1 says: "Validates: Automated scanning vs targeted Exchange exploitation"
→ H1: "Is this automated vulnerability scanning or a targeted Exchange exploitation attempt?"

Step 1 says: "Focus on: PowerShell execution indicators"
→ H2: "Did PowerShell successfully execute on the Exchange server?"
```

## Cy Script Pattern

```cy
# Static hypotheses from runbook (baked in during Kea)
# These are extracted from the runbook and hardcoded at task creation time
runbook_hypotheses = [
  {
    "id": "H1",
    "question": "Is this automated scanning or targeted exploitation?",
    "validates": "Attack intent classification",
    "evidence_sources": ["threat_intel_enrichment", "payload_analysis"]
  },
  {
    "id": "H2",
    "question": "Did the attack successfully execute on the target?",
    "validates": "Exploitation success",
    "evidence_sources": ["edr_analysis", "siem_logs"]
  }
]

# Get alert context from previous step
alert_context = input.enrichments?.alert_context?.context_summary ?? input.title

# LLM evaluates and augments
result = llm_run(
  directive="""You are forming investigation hypotheses for this alert.

Starting hypotheses (from investigation playbook):
${runbook_hypotheses}

Current alert context:
${alert_context}

Tasks:
1. Evaluate if these hypotheses are appropriate for THIS specific alert
2. Add any additional hypotheses this specific alert inspires (unique characteristics)
3. Return the complete hypothesis list

Return JSON (no markdown):
{
  "hypotheses": [
    {"id": "H1", "question": "...", "validates": "...", "evidence_sources": [...], "source": "runbook"},
    {"id": "HA1", "question": "...", "validates": "...", "evidence_sources": [...], "source": "alert_inspired"}
  ]
}""",
  data={"alert": input}
)

return enrich_alert(input, {
  "investigation_hypotheses": result.hypotheses,
  "hypothesis_source": {
    "from_runbook": runbook_hypotheses,
    "alert_inspired": result.hypotheses | filter(h => h.source == "alert_inspired")
  }
})
```

## Task Proposal Format (Phase 2)

When proposing a hypothesis task in Phase 2, include:

```json
{
  "name": "ProxyNotShell Hypothesis Generation",
  "designation": "new",
  "description": "Purpose: Generate investigation hypotheses that guide the analysis. This task combines static hypotheses from the runbook with dynamic, alert-specific questions.

STATIC HYPOTHESES (from runbook):
- H1: Is this automated vulnerability scanning or a targeted Exchange exploitation attempt?
- H2: Did PowerShell successfully execute on the Exchange server (confirming CVE-2022-41082 RCE)?
- H3: Was the SSRF component (CVE-2022-41040) successful in accessing the backend?
- H4: Did the attacker establish outbound C2 communication from the Exchange server?

HYPOTHESIS JSON SCHEMA:
{
  \"id\": \"string (H1, H2, etc.)\",
  \"question\": \"string (yes/no investigative question)\",
  \"validates\": \"string (what this hypothesis helps determine)\",
  \"evidence_sources\": [\"string (which tasks/enrichments provide evidence)\"]
}

Process: Present static hypotheses to LLM along with alert context. LLM evaluates if these cover this specific alert or if unique characteristics warrant additional hypotheses.

Inputs: enrichments.alert_context from alert_context_generation.
Outputs: enrichments.investigation_hypotheses array of hypothesis objects with source attribution (from_runbook vs alert_inspired).",
  "integration-mapping": null
}
```

## Building the Task (Phase 3)

When Phase 3 receives a hypothesis task proposal:

1. **Extract static hypotheses** from the task description's "STATIC HYPOTHESES" section
2. **Convert to array literal** in Cy script (hardcoded, not fetched at runtime)
3. **Use the Cy Script Pattern** above as template
4. **Include the JSON schema** in the LLM directive so it returns properly formatted hypotheses

**Task metadata:**
```json
{
  "name": "...",
  "function": "reasoning",
  "scope": "processing",
  "app": "default",
  "directive": "You are forming investigation hypotheses..."
}
```

## Workflow Position

Hypothesis generation tasks run:
- AFTER `alert_context_generation` (needs alert context)
- BEFORE investigation tasks (hypotheses guide investigation)

```
alert_context_generation → hypothesis_generation → [investigation tasks] → triad
```

## Validation

Hypothesis tasks MUST:
- Output `investigation_hypotheses` array in enrichments
- Each hypothesis follows the JSON schema
- Include source attribution (`from_runbook` vs `alert_inspired`)
- Use `enrich_alert()` to preserve existing enrichments
