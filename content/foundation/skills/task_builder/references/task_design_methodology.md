# Task Design Methodology: Minimalist Approach

## Overview

This document provides the methodology for designing **minimal, focused tasks**. The key principle is: **Less Is More**.

## 🎯 Core Principle: Do Less

```
╔══════════════════════════════════════════════════════════════╗
║ MINIMALIST TASK DESIGN                                       ║
╠══════════════════════════════════════════════════════════════╣
║ ❌ AVOID: Computing ratios, percentages, derived metrics    ║
║ ❌ AVOID: Classifying numeric ranges (0-10=low, 11-50=med)  ║
║ ❌ AVOID: Complex multi-step extraction fallbacks           ║
║                                                              ║
║ ✅ DO: Answer ONE specific investigative question           ║
║ ✅ DO: Let LLM interpret raw values contextually            ║
║ ✅ DO: Return raw integration data for downstream flex      ║
╚══════════════════════════════════════════════════════════════╝
```

## When to Split Tasks

Before building, ask if this task is trying to do too much.

**Signs a task should be split:**
- Calling 2+ different integrations (each can be its own task)
- Performing multiple analytical questions
- Script exceeds 80 lines (simpler is better)
- Computing derived metrics that could be left to LLM
- Adding "nice to have" features beyond core objective

**Example of task that should be split:**
```
❌ BAD: "comprehensive_threat_analysis"
- Calls VirusTotal, AbuseIPDB, Shodan, GreyNoise
- Checks user privileges in AD LDAP
- Analyzes EDR process tree
- Correlates SIEM events
- Determines disposition

✅ GOOD: Split into focused tasks
- "multi_source_ip_reputation_correlation" (threat intel only)
- "ad_ldap_privileged_user_check" (identity only)
- "echo_edr_behavioral_analysis" (endpoint only)
- "splunk_supporting_evidence_search" (SIEM only)
- "alert_disposition_determination" (synthesis only)
```

**Why split matters:**
- Each task is independently testable
- Tasks can be reused across workflows
- Parallel execution improves performance
- Easier to debug and maintain

## Simplified Task Structure

Most minimal tasks follow a simple pattern:

```
Alert → Extract Fields → Call Integration → (Optional) LLM Analysis → Return Enriched Alert
```

**Keep it simple:** Many tasks don't need LLM analysis at all - just integration data retrieval and additive enrichment.

## Step 1: Safe Input Projection and Guards (MANDATORY)

**Purpose:** Extract required fields from input alert with null-safe guards and validation.

**What to do:**
- Project the specific fields your task needs
- Add null checks and default values
- Extract alert context (from `alert_context_generation` task)
- Validate input has minimum required data
- Return early if prerequisites missing

**Example:**
```cy
# Extract alert context (mandatory for LLM tasks)
alert_context = input.enrichments?.alert_context?.context_summary ??
                input.title ??
                input.finding_info.title ??
                "Unknown alert"

# Extract required fields with guards
source_ip = get_src_ip(input) ?? null
if (source_ip == null) {
    # Missing required field - return alert unchanged
    return input
}

# Extract optional enrichments from previous tasks
user_context = input.enrichments?.ad_ldap_user_context ?? null
has_user_context = user_context != null
```

**Key Principles:**
- **Always extract alert_context first** (for downstream LLM steps)
- **Use null-safe navigation** (`?.` and `??`)
- **Validate before proceeding** (return early if missing critical data)
- **Don't assume previous enrichments exist** (handle missing gracefully)

## Step 2: LLM Input Composition/Revision (OPTIONAL)

**Purpose:** Use LLM to intelligently prepare or refine inputs for integration tools based on alert context.

**When to use Step 2:**
- Integration tool accepts complex queries (Splunk SPL, search patterns)
- Multiple search strategies possible based on alert type
- Need to determine which fields to search for
- Need to generate smart search parameters

**When to skip Step 2:**
- Simple field lookups (IP reputation, hash lookup)
- Fixed query patterns
- No decision-making needed for input preparation

### Example 1: LLM-Generated Splunk Query

```cy
# Step 1: Already extracted alert_context and source_ip

# Step 2: Use LLM to compose smart Splunk search
search_strategy = llm_run(
    directive="""You are a Splunk expert helping investigate a security alert.

    Alert Context: ${alert_context}
    Source IP: ${source_ip}

    Generate a Splunk search strategy to find supporting evidence. Consider:
    - What time window to search (based on alert timing)
    - What indexes to target (based on alert type)
    - What fields to correlate (source IP, destination, user, process)
    - What patterns indicate related activity

    Return a JSON object with:
    {
        "time_window": "e.g., -15m to +5m from alert",
        "indexes": ["index1", "index2"],
        "search_fields": ["src_ip", "dest_ip", "action"],
        "rationale": "Why this search strategy"
    }
    """
)

# Parse LLM strategy and use it to build SPL query
time_window = search_strategy.time_window
indexes_str = " OR ".join(search_strategy.indexes)
spl_query = """search index IN (${indexes_str}) src_ip="${source_ip}"
               earliest="${time_window.start}" latest="${time_window.end}"
               | stats count by src_ip, dest_ip, action"""
```

### Example 2: LLM-Determined Search Fields

```cy
# Step 1: Already extracted alert_context and alert fields

# Step 2: LLM decides what to search for
search_plan = llm_run(
    directive="""Alert Context: ${alert_context}

    This alert contains: IP=${source_ip}, User=${username}, Hash=${file_hash}

    Which indicators should we enrich with threat intelligence?
    Return JSON: {"primary_indicators": ["ip", "hash"], "rationale": "why"}
    """
)

# Use LLM decision to determine which APIs to call
should_check_ip = "ip" in search_plan.primary_indicators
should_check_hash = "hash" in search_plan.primary_indicators
```

**Benefits of Step 2:**
- **Context-aware queries:** Search strategy adapts to alert type
- **Reduced noise:** Smarter searches return more relevant results
- **Better coverage:** LLM identifies relevant search dimensions
- **Flexibility:** Same task adapts to different alert scenarios

## Step 3: Tool and Integration Context Enrichment (MANDATORY)

**Purpose:** Call integration tools or native functions to gather objective data.

**What to do:**
- Call integration tools (VirusTotal, AbuseIPDB, Splunk, EDR)
- Use native Cy functions (url_decode, regex_match, etc.)
- Extract only relevant fields from tool responses (avoid verbose outputs)
- Handle errors gracefully (tool failures shouldn't break task)

**Example:**
```cy
# Step 1 & 2: Already have alert_context, source_ip, and search strategy

# Step 3: Call integration to gather data
vt_result = app::virustotal::ip_reputation(ip=source_ip)

# Project only relevant fields (don't pass entire API response to LLM)
threat_indicators = {
    "malicious_count": vt_result.data.attributes.last_analysis_stats.malicious,
    "suspicious_count": vt_result.data.attributes.last_analysis_stats.suspicious,
    "total_engines": vt_result.data.attributes.last_analysis_stats.total,
    "reputation": vt_result.data.attributes.reputation,
    "country": vt_result.data.attributes.country
}

# Handle integration errors
if (vt_result.error != null) {
    threat_indicators = {
        "error": vt_result.error,
        "data_available": false
    }
}
```

**Key Principles:**
- **Project relevant fields only:** Don't pass 5KB API responses to LLMs
- **Handle errors:** Integration failures are normal, handle gracefully
- **Multiple tools:** Can call multiple integrations in this step
- **Native functions:** Use built-in Cy functions

**Field Projection Examples:**

❌ **BAD - Passing entire response:**
```cy
vt_result = app::virustotal::ip_reputation(ip=source_ip)
analysis = llm_run(directive="...", data=vt_result)  # 3000+ tokens!
```

✅ **GOOD - Project relevant fields:**
```cy
vt_result = app::virustotal::ip_reputation(ip=source_ip)
threat_summary = {
    "detection_ratio": vt_result.data.attributes.last_analysis_stats.malicious,
    "reputation": vt_result.data.attributes.reputation
}
analysis = llm_run(directive="...", data=threat_summary)  # 50 tokens
```

## Step 4: LLM Validation or Question Generation (MANDATORY for Analysis Tasks)

**Purpose:** Use LLM to reason about the enrichment data in the context of the original alert.

**What to do:**
- Pass alert_context + enrichment data (from Step 3) to LLM
- Ask LLM to validate hypothesis or answer analytical question
- Frame as hypothesis validation: "Does this data support/refute the alert?"
- Or frame as question generation: "What new questions does this raise?"
- Extract structured conclusions from LLM response

### Example: Hypothesis Validation

```cy
# Step 3: Already gathered threat_indicators

# Step 4: LLM validates hypothesis
analysis = llm_run(
    directive="""You are a security analyst investigating an alert.

    Alert Context: ${alert_context}

    IP Reputation Data:
    - Detection Ratio: ${threat_indicators.malicious_count}/${threat_indicators.total_engines}
    - Reputation Score: ${threat_indicators.reputation}
    - Country: ${threat_indicators.country}

    HYPOTHESIS: This IP is malicious and poses a threat.

    Validate this hypothesis:
    1. Does the reputation data support or refute the hypothesis?
    2. What is the confidence level (low/medium/high)?
    3. What is the risk level (low/medium/high/critical)?
    4. What additional evidence would strengthen the conclusion?

    Be specific about how the data relates to the alert context."""
)

# Extract structured conclusions using regex or parsing
risk_level = "medium"  # Default
if (regex_match(lowercase(analysis), ".*(high risk|critical).*")) {
    risk_level = "high"
} elif (regex_match(lowercase(analysis), ".*(low risk|benign).*")) {
    risk_level = "low"
}
```

### Example: Question Generation

```cy
# Step 4: LLM generates follow-up questions
follow_up = llm_run(
    directive="""Based on the alert context and IP reputation findings:

    Alert: ${alert_context}
    Findings: IP has ${threat_indicators.malicious_count} malicious detections

    What additional investigative questions should we answer?
    Generate 2-3 specific questions that would help determine alert severity.

    Format: ["Question 1?", "Question 2?", "Question 3?"]
    """
)
```

**Key Principles:**
- **Always include alert_context:** Provides focus and relevance
- **Hypothesis framing:** More effective than open-ended "analyze this"
- **Structured outputs:** Ask for specific conclusions (risk level, confidence, rationale)
- **Relevant only:** Only pass data relevant to the analytical question

## Complete Example: Splunk Supporting Evidence Search

This example demonstrates all 4 steps working together:

```cy
# ============================================
# Step 1: Safe Input Projection and Guards
# ============================================

alert = input

# Extract alert context (mandatory)
alert_context = alert.enrichments?.alert_context?.context_summary ??
                alert.title ??
                alert.finding_info.title ??
                "Unknown alert"

# Extract required fields
alert_id = alert.alert_id ?? "unknown"
alert_type = alert.alert_type ?? "unknown"
source_ip = get_src_ip(alert) ?? null
dest_ip = get_dst_ip(alert) ?? null
triggering_time = alert.triggering_event_time ?? null

# Validate prerequisites
if (triggering_time == null) {
    # Can't search without timestamp
    return alert
}

# Build IOC list for search
iocs = []
if (source_ip != null) {
    iocs.append({"type": "ip", "value": source_ip, "field": "src_ip"})
}
if (dest_ip != null) {
    iocs.append({"type": "ip", "value": dest_ip, "field": "dest_ip"})
}

# ============================================
# Step 2: LLM Input Composition (Optional)
# ============================================

# Use LLM to generate smart Splunk search strategy
search_strategy = llm_run(
    directive="""You are a Splunk expert investigating a security alert.

    Alert Context: ${alert_context}
    Alert Type: ${alert_type}
    Available IOCs: ${iocs}
    Alert Time: ${triggering_time}

    Generate a Splunk search strategy to find supporting evidence:
    1. What time window to search? (consider attack patterns)
    2. What should we correlate on? (same source, same dest, payload patterns)
    3. What fields indicate related activity?

    Return JSON:
    {
        "time_before_minutes": 15,
        "time_after_minutes": 5,
        "correlation_fields": ["src_ip", "dest_ip", "http_method"],
        "search_hypothesis": "Looking for multiple requests with same pattern",
        "rationale": "Why this strategy"
    }
    """
)

# Build SPL query using LLM strategy
time_before = search_strategy.time_before_minutes
time_after = search_strategy.time_after_minutes
correlation_fields = search_strategy.correlation_fields

# Build search constraints
constraints = []
for ioc in iocs:
    if (ioc.field in correlation_fields) {
        constraints.append("""${ioc.field}="${ioc.value}"""")
    }
}
constraint_str = " OR ".join(constraints)

spl_query = """search index=* (${constraint_str})
               earliest=-${time_before}m@s latest=+${time_after}m@s
               | stats count by ${", ".join(correlation_fields)}
               | sort -count"""

# ============================================
# Step 3: Tool and Integration Enrichment
# ============================================

# Execute Splunk search
search_result = app::splunk::run_search(
    query=spl_query,
    earliest_time="-${time_before}m",
    latest_time="+${time_after}m"
)

# Project only relevant fields (don't pass 10MB of logs to LLM)
evidence_summary = {
    "total_events": search_result.result_count ?? 0,
    "search_strategy": search_strategy.search_hypothesis,
    "query_used": spl_query
}

# Extract key patterns from results (first 10 events only)
if (search_result.results != null && len(search_result.results) > 0) {
    evidence_summary["sample_events"] = search_result.results[:10]
    evidence_summary["patterns_found"] = true
} else {
    evidence_summary["patterns_found"] = false
}

# ============================================
# Step 4: LLM Validation and Analysis
# ============================================

# Use LLM to analyze evidence and validate hypothesis
analysis = llm_run(
    directive="""You are analyzing supporting evidence for a security alert.

    Alert Context: ${alert_context}

    Search Strategy: ${evidence_summary.search_strategy}

    Evidence Found:
    - Total Related Events: ${evidence_summary.total_events}
    - Patterns Detected: ${evidence_summary.patterns_found}
    - Sample Events: ${evidence_summary.sample_events}

    HYPOTHESIS: This alert is part of a larger attack pattern.

    Validate the hypothesis:
    1. Does the evidence support a sustained attack? (yes/no/insufficient)
    2. What patterns indicate coordinated activity?
    3. Does the volume/timing suggest automation or manual attack?
    4. What is the confidence level in the hypothesis?

    Provide analysis in 3-4 sentences."""
)

# Extract confidence from analysis
confidence = "medium"
if (regex_match(lowercase(analysis), ".*(strong evidence|confirms|definitely).*")) {
    confidence = "high"
} elif (regex_match(lowercase(analysis), ".*(weak evidence|insufficient|unclear).*")) {
    confidence = "low"
}

# ============================================
# Return: Additive Enrichment
# ============================================

# Add enrichment to alert (preserve existing)
enrichments = alert.enrichments ?? {}
enrichments["splunk_supporting_evidence"] = {
    "data_source": "Splunk Supporting Evidence Search",
    "search_strategy": search_strategy,
    "evidence_summary": evidence_summary,
    "hypothesis_validation": analysis,
    "confidence": confidence,
    "query_used": spl_query
}
alert["enrichments"] = enrichments

return alert
```

## Decision Tree: When to Use Each Step

**Step 1: Safe Input Projection** → ✅ ALWAYS (mandatory for all tasks)

**Step 2: LLM Input Composition** → Use when:
- ✅ Integration accepts complex queries (Splunk SPL, search patterns)
- ✅ Multiple search strategies possible
- ✅ Need to determine WHAT to search for based on alert context
- ✅ Need to adapt query parameters to alert type
- ❌ Skip for simple lookups (IP reputation, hash lookup)
- ❌ Skip for fixed query patterns

**Step 3: Tool/Integration Enrichment** → ✅ ALWAYS (core task purpose)

**Step 4: LLM Validation/Analysis** → Use when:
- ✅ Task performs analysis or correlation
- ✅ Need to interpret results in context
- ✅ Determining risk, confidence, or recommendations
- ❌ Skip for simple data retrieval tasks (raw SIEM event fetch)
- ❌ Skip when data speaks for itself (numeric scores)

## Benefits of the 4-Step Pattern

- **Clarity:** Each step has clear purpose and boundaries
- **Testability:** Can test each step independently
- **Maintainability:** Easy to debug - identify which step failed
- **Flexibility:** Steps can be added/removed based on task needs
- **Performance:** Can optimize each step (caching, parallel calls)
- **Reusability:** Steps follow common patterns across tasks

## Security-Informed Directives

When writing LLM directives (Steps 2 and 4), use the `cybersecurity-analyst` skill to create security-informed prompts:

### Bad Directive (Generic)
```cy
directive = "Analyze the login data and provide a summary."
```

### Good Directive (Security-Informed)
```cy
directive = """You are a security analyst investigating suspicious login activity.

Analyze login patterns for these specific threats:
1. Credential stuffing: Failed attempts followed by success from same IP
2. Geographic anomalies: Login from unusual countries or Tor/VPN
3. Privilege escalation: Elevated access shortly after login
4. Timing anomalies: Off-hours access, rapid succession from multiple IPs

Provide risk assessment (2-3 sentences) with:
- Specific evidence (counts, IPs, timings)
- Threat classification (credential stuffing, account takeover, insider threat)
- Recommended action (escalate, monitor, close as benign)"""
```

**Key Improvements:**
- **Specific threat patterns** instead of generic "analyze data"
- **Investigation priorities** relevant to login alerts
- **Actionable output format** with classification and recommendations
- **Security terminology** that aligns with SOC analyst workflows

## Summary

The 4-step pattern provides a structured approach to building tasks that:
1. **Safely extract** required data with validation
2. **Intelligently prepare** inputs when complexity warrants it
3. **Gather data** from integrations with proper field projection
4. **Analyze contextually** with hypothesis-driven LLM reasoning

This methodology ensures tasks are focused, testable, and produce consistent, high-quality results.
