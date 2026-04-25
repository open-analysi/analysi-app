# Task Dependencies and Alert Context Pattern

## Overview

Tasks in Analysi Security are designed to work collectively, building upon each other's outputs to create comprehensive alert analysis workflows. This document explains the critical pattern of task dependencies, particularly the foundational Alert Context Generator pattern.

**Core Principle:** Tasks don't work in isolation - they build on previous tasks' enrichments to make progressively more informed decisions.

---

## The Alert Context Generator Pattern

### What It Is

The Alert Context Generator is a foundational task that runs FIRST in most workflows. It creates a human-readable summary of the alert that subsequent tasks use to understand what they're investigating and why.

### Why It Matters

Without context, each task would need to:
- Re-analyze the entire alert structure
- Duplicate context extraction logic
- Make decisions without understanding the bigger picture
- Waste tokens re-discovering what the alert is about

With the Alert Context Generator pattern:
- Context is extracted once and reused
- All tasks share a common understanding
- LLM reasoning is informed by alert context
- Decisions are consistent across the workflow

---

## How the Pattern Works

### Step 1: Alert Context Generator Runs First

The workflow builder ensures the Alert Context Generator task runs before dependent tasks:

```json
// Workflow composition
[
  "alert_context_generator",      // MUST run first
  ["ip_reputation", "user_lookup"], // Can run in parallel after context
  "merge",
  "risk_correlation"               // Uses context + enrichments
]
```

### Step 2: Context Gets Added to Enrichments

The Alert Context Generator adds this structure to `input.enrichments.alert_context_generation`:

```json
{
  "enrichments": {
    "alert_context_generation": {
      "data_source": "Alert Context Generator",
      "ai_analysis": "Suspicious login detected from IP 185.220.101.45 for user jsmith at 3:15 AM. Multiple failed attempts followed by successful authentication from Tor exit node.",
      "context_length": 287,
      "completeness_score": 85,
      "metadata": {
        "has_ioc": true,
        "has_risk_entity": true,
        "has_action": true
      }
    }
  }
}
```

### Step 3: Subsequent Tasks Use the Context

Tasks that run after the Alert Context Generator can access this context:

```cy
# Every task after context generator can access:
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? ""

# Use context to inform LLM reasoning
analysis = llm_run(
    directive="""You are analyzing IP reputation data for a security alert.

    Alert Context: ${alert_context}

    Based on this context, analyze the IP reputation data and determine:
    1. Is this IP relevant to the alert described?
    2. Does the reputation align with the suspicious activity?
    3. What risk does this IP pose in this specific context?
    """,
    data={
        "ip": ip,
        "reputation_data": vt_results
    }
)
```

---

## Required Pattern for LLM Tasks

### CRITICAL RULE: Always Include Context in LLM Directives

When asking an LLM to make decisions about tool results, **ALWAYS** include the alert context to explain why we care about the analysis.

#### ❌ BAD - No Context:
```cy
# Missing context - LLM doesn't know why we're checking this IP
analysis = llm_run(
    directive="Analyze this IP reputation data and determine if it's malicious.",
    data={"ip": ip, "reputation": vt_results}
)
```

#### ✅ GOOD - With Context:
```cy
# Context informs the LLM why this matters
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? ""

analysis = llm_run(
    directive="""You are analyzing IP reputation data for a security alert.

    Alert Context: ${alert_context}

    Based on this context, analyze the IP reputation data to determine:
    1. Relevance to the described alert
    2. Alignment with the suspicious activity mentioned
    3. Risk level in this specific context
    """,
    data={"ip": ip, "reputation": vt_results}
)
```

---

## Implementing Task Dependencies

### Pattern 1: Checking for Required Context

Use null-safe navigation to handle cases where context might not exist:

```cy
# Safe access with fallback
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? "No context available"

# Check if context exists before using
has_context = input.enrichments.alert_context_generation != null
if (has_context) {
    # Use full context
    context_summary = input.enrichments.alert_context_generation.ai_analysis
    completeness_score = input.enrichments.alert_context_generation.completeness_score
} else {
    # Fallback behavior
    context_summary = "Alert context not available. Analyzing based on provided data only."
}
```

### Pattern 2: Building on Multiple Task Outputs

Tasks can depend on multiple previous enrichments:

```cy
# Access context from Alert Context Generator
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? ""

# Access IP reputation from previous task
ip_reputation = input.enrichments?.ip_reputation_analysis ?? {}

# Access user info from another task
user_risk = input.enrichments?.user_privilege_check ?? {}

# Combine all context for informed decision
analysis = llm_run(
    directive="""Correlate findings from multiple sources.

    Alert Context: ${alert_context}

    Previous Findings:
    - IP Reputation: ${ip_reputation.risk_level ?? "unknown"}
    - User Risk: ${user_risk.privilege_level ?? "unknown"}

    Determine overall risk and recommended action.
    """,
    data={
        "all_enrichments": input.enrichments
    }
)
```

---

## Task Dependency Patterns

### Pattern 1: Sequential Dependencies (Context → Analysis)

```cy
# Task 2 depends on Task 1's context
alert_context = input.enrichments.alert_context_generation.ai_analysis

# Use context to guide analysis
results = app::virustotal::ip_reputation(ip=ip)

analysis = llm_run(
    directive="Given this alert context: ${alert_context}\n\nAnalyze the IP reputation...",
    data=results
)
```

### Pattern 2: Parallel After Context (Context → [Task A, Task B])

Multiple tasks can run in parallel after context is established:

```json
// Workflow composition
[
  "alert_context_generator",       // Runs first
  [                                // These run in parallel after context
    "ip_reputation_check",
    "user_privilege_lookup",
    "splunk_event_retrieval"
  ],
  "merge",                         // Combines all results
  "risk_correlation"               // Uses everything
]
```

### Pattern 3: Progressive Enhancement

Each task adds to the enrichments, building a complete picture:

```cy
# Task 1: Adds context
input.enrichments.alert_context_generation = {
    "ai_analysis": "...",
    "completeness_score": 85
}

# Task 2: Adds IP analysis (uses context)
input.enrichments.ip_analysis = {
    "risk_score": 95,
    "is_tor": true,
    "context_relevance": "High - matches alert context"
}

# Task 3: Correlates everything
input.enrichments.risk_correlation = {
    "overall_risk": "Critical",
    "confidence": 0.92,
    "reasoning": "Based on context and IP analysis..."
}
```

---

## Best Practices

### 1. Always Check for Context Availability

```cy
# Use null-safe navigation
context = input.enrichments.alert_context_generation.ai_analysis ?? "No context"
```

### 2. Include Context in Every LLM Directive

```cy
# Context should be first thing in directive
directive = """Alert Context: ${alert_context}

Now analyze the following data..."""
```

### 3. Document Task Dependencies

In your task description:
```json
{
  "name": "IP Reputation Analysis",
  "description": "Analyzes IP reputation using VirusTotal. REQUIRES: alert_context_generator to run first.",
  "dependencies": ["alert_context_generator"]  // Future field
}
```

### 4. Test with and without Context

Your data_samples should include both scenarios:

```json
{
  "data_samples": [
    {
      "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
      "enrichments": {
        "alert_context_generation": {
          "ai_analysis": "Suspicious login from Tor exit node"
        }
      }
    },
    {
      "observables": [{"value": "8.8.8.8", "type": "IP Address"}],
      "enrichments": {}  // Test without context
    }
  ]
}
```

---

## Example: Complete Task Using Context Pattern

```cy
# Task: IP Reputation Analysis with Context-Aware LLM Reasoning

# Step 1: Extract context (from Alert Context Generator task)
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                "No alert context available. Analyzing IP in isolation."

# Step 2: Extract IP to analyze
ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? null
if (ip == null) {
    return {"error": "No IP address found to analyze"}
}

# Step 3: Get reputation data
vt_results = app::virustotal::ip_reputation(ip=ip)

# Step 4: Context-aware LLM analysis
analysis = llm_run(
    directive="""You are a security analyst investigating an IP address.

    ALERT CONTEXT: ${alert_context}

    Analyze the IP reputation data considering the alert context above.

    Provide:
    1. Is this IP relevant to the alert context? (Yes/No and why)
    2. Risk assessment specific to this alert (Critical/High/Medium/Low)
    3. Key findings that relate to the context (2-3 bullets)
    4. Recommended action based on context + reputation

    Be concise but specific about how the IP reputation relates to the alert.
    """,
    data={
        "ip_address": ip,
        "reputation": vt_results,
        "has_context": alert_context != "No alert context available."
    }
)

# Step 5: Enrich alert with context-aware analysis
input.enrichments = input.enrichments ?? {}
input.enrichments.ip_reputation_analysis = {
    "ip": ip,
    "risk_assessment": analysis,
    "used_context": alert_context != "No alert context available.",
    "reputation_score": vt_results.malicious_votes ?? 0
}

return input
```

---

## Workflow Composition Considerations

### Tasks That MUST Run After Context Generator:
- Risk correlation tasks
- Disposition recommendation tasks
- Summary generation tasks (final)
- Any task using LLM to interpret findings

### Tasks That CAN Run Without Context:
- Pure data retrieval (get_notable_event)
- Direct integration queries (raw API calls)
- Simple data extraction tasks

### Tasks That BENEFIT From Context:
- All enrichment tasks with LLM analysis
- Reputation checking with interpretation
- User activity analysis with risk assessment
- Network traffic analysis with threat detection

---

## Troubleshooting

### Context Not Available

If `input.enrichments.alert_context_generation` is null:
1. Check workflow composition - is alert_context_generator first?
2. Verify the context generator task succeeded
3. Use fallback: `?? "No context available"`

### Context Too Long

If context_summary is very long:
```cy
# Truncate if needed
context = input.enrichments.alert_context_generation.ai_analysis ?? ""
if (context.length > 500) {
    context = context.substring(0, 497) + "..."
}
```

### Testing Dependencies

Test your task with various context states:
```json
// Test 1: With full context
{
  "enrichments": {
    "alert_context_generation": {
      "ai_analysis": "Suspicious activity detected...",
      "completeness_score": 95
    }
  }
}

// Test 2: Without context
{
  "enrichments": {}
}

// Test 3: With partial context
{
  "enrichments": {
    "alert_context_generation": {
      "ai_analysis": "",
      "completeness_score": 20
    }
  }
}
```

---

## Summary

The Alert Context Generator pattern is fundamental to building effective security automation tasks:

1. **Context runs first** - Workflow builder ensures proper ordering
2. **Context informs everything** - All subsequent tasks can access the summary
3. **LLM decisions need context** - Always include alert_context in directives
4. **Tasks build on each other** - Progressive enhancement through enrichments
5. **Handle missing context gracefully** - Use null-safe navigation with fallbacks

By following this pattern, tasks work together as a cohesive system rather than isolated components, creating more intelligent and context-aware security automation.
