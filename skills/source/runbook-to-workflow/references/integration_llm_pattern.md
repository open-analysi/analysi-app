# Integration + LLM Reasoning Pattern

## Overview

The **Integration + LLM Reasoning Pattern** is the core architectural approach for building Analysi Security Tasks. Almost all tasks follow this two-step pattern that combines the precision of integration tools with the intelligence of LLM reasoning.

## The Pattern

```
1. Data Retrieval: Pull raw data from integration tools
2. LLM Analysis: Use LLM to reason about the data and provide security-informed analysis
```

## Why This Pattern Works

### Precision (Integration Tools)
- Provide accurate, structured data from authoritative sources
- Consistent, reliable data retrieval
- Direct access to ground truth (EDR processes, SIEM events, TI reputation)

### Intelligence (LLM Reasoning)
- Context-aware analysis of the data
- Security expertise applied to interpretation
- Natural language summaries for analysts
- Pattern recognition and anomaly detection

## Examples from ProxyNotShell Investigation

### Example 1: EDR Process Analysis
```cy
# Step 1: Data Retrieval (Integration)
processes = app::echo_edr::pull_processes(
    ip=target_ip,
    start_time=attack_time,
    end_time=end_time
)

# Step 2: LLM Analysis (Reasoning)
process_analysis = llm_run(
    directive="""You are an EDR analyst reviewing post-attack process activity.

    Analyze the process list for signs of successful exploitation:
    1. Suspicious process names (powershell.exe, cmd.exe from unusual paths)
    2. Process injection or code execution
    3. Unexpected child processes from Exchange services (w3wp.exe)

    For ProxyNotShell, successful exploitation would show:
    - PowerShell spawned by w3wp.exe
    - Command execution with suspicious arguments

    Verdict: MALICIOUS ACTIVITY / SUSPICIOUS ACTIVITY / CLEAN
    """,
    data={
        "processes": processes,
        "target_ip": target_ip,
        "alert_context": alert_context
    }
)
```

### Example 2: CVE Understanding
```cy
# Step 1: Data Retrieval (Integration)
cve_data = app::nistnvd::get_cve_details(
    cve_id="CVE-2022-41082"
)

# Step 2: LLM Analysis (Reasoning)
cve_analysis = llm_run(
    directive="""Analyze the CVE data and provide:
    1. What systems/software versions are vulnerable?
    2. What is the attack method/exploit technique?
    3. How recent is this CVE? (timeline analysis)
    4. What is the severity and impact?

    Provide concise 3-4 sentence summary for SOC analyst use.
    """,
    data={
        "cve_id": cve_ids[0],
        "cve_details": cve_data,
        "alert_context": alert_context
    }
)
```

### Example 3: Threat Intelligence Analysis
```cy
# Step 1: Data Retrieval (Integration)
abuse_data = app::abuseipdb::check_ip(
    ip=attacker_ip
)

# Step 2: LLM Analysis (Reasoning)
ti_analysis = llm_run(
    directive="""Interpret the AbuseIPDB reputation data:
    1. What is the abuse confidence score? (0-100)
    2. What types of abuse have been reported?
    3. How recent are the reports?
    4. Is this a known malicious actor or first-time offender?

    Provide security analyst-friendly interpretation.
    """,
    data={
        "ip": attacker_ip,
        "abuse_data": abuse_data,
        "alert_context": alert_context
    }
)
```

## Task Types and Pattern Usage

### Type 1: Integration + LLM (Most Common)
**Tasks that query external systems and analyze the results**
- EDR process/command analysis
- CVE metadata analysis
- Threat intelligence reputation checks
- SIEM event correlation
- Asset profiling (LDAP + analysis)

**Pattern:**
1. Call `app::{integration}::{tool}()` to get data
2. Call `llm_run()` with security-focused directive
3. Enrich alert with both raw data and analysis

### Type 2: LLM-Only (Synthesis)
**Tasks that combine existing enrichments without new data retrieval**
- Alert context generation (initial summary)
- Multi-source correlation (combine TI from VirusTotal + AbuseIPDB)
- Attack relevance assessment (combine CVE + target profile)
- Final reporting (synthesis of all enrichments)
- Disposition decision

**Pattern:**
1. Extract existing enrichments from `input.enrichments`
2. Call `llm_run()` with synthesis directive
3. Enrich alert with synthesized insights

### Type 3: Integration-Only (Rare)
**Tasks that only retrieve data without analysis**
- Triggering event retrieval (raw SIEM events)
- Supporting event search (raw log data)

**Pattern:**
1. Call integration tool
2. Store raw data in enrichments
3. No LLM analysis (data used by downstream tasks)

## When to Use Each Type

| Task Purpose | Pattern | Reasoning |
|-------------|---------|-----------|
| Get external data + interpret | Integration + LLM | Need both data and security expertise |
| Combine existing enrichments | LLM-Only | Already have data, need synthesis |
| Retrieve raw data for later | Integration-Only | Downstream tasks will analyze it |

## Best Practices

### DO:
- **Always provide alert context to LLM** - Use `input.enrichments?.alert_context?.context_summary` in directives
- **Write security-informed directives** - LLM should reason like a SOC analyst
- **Include specific guidance in directives** - What to look for, how to interpret, what verdict format
- **Use null-safe navigation** - `input.enrichments?.field ?? "default"` (Cy 0.21 syntax)
- **Enrich additively** - Never overwrite existing enrichments, always append

### DON'T:
- **Don't skip LLM analysis for complex data** - Raw integration output isn't analyst-friendly
- **Don't write vague directives** - "Analyze this" is too generic
- **Don't forget to pass alert context** - LLM needs case context for relevance
- **Don't duplicate effort** - If another task already got the data, use LLM-only synthesis

## Integration + LLM Pattern in data_samples

When creating data_samples for tasks using this pattern:

```json
[
  {
    "evidences": [
      {
        "dst_endpoint": {"ip": "10.10.30.8"}
      }
    ],
    "time": "2026-04-26T07:19:00Z",
    "enrichments": {
      "alert_context": {
        "context_summary": "ProxyNotShell attack on Exchange Server"
      }
    }
  }
]
```

**Key points:**
- Include only fields the integration tool needs (IP, timestamp, etc.)
- Include `alert_context` for LLM directives
- Don't include fields the task doesn't access
- See `references/data_samples_guide.md` in task-builder skill for details

## Task Notation in Results

When documenting tasks that use this pattern, use arrow notation:

- ✅ `edr_processes_after_attack` **(echo_edr → LLM analysis)**
- ✅ `cve_understanding_nistnvd` **(nistnvd → LLM analysis)**
- ✅ `abuseipdb_ip_reputation_analysis` **(abuseipdb → LLM analysis)**
- ✅ `multi_source_ip_reputation_correlation` **(LLM synthesis)**
- ✅ `alert_context_generation` **(LLM analysis of OCSF alert)**

This notation makes it immediately clear:
- Which integration is queried (if any)
- That LLM reasoning follows
- Tasks that are LLM-only synthesis

## Real-World Impact

This pattern enables:
- **Automation with intelligence** - Not just data retrieval, but interpretation
- **Consistency** - Every analyst gets same expert reasoning
- **Scalability** - LLM can analyze thousands of alerts with same quality
- **Adaptability** - Can reason about novel attack patterns

The combination of reliable data (integrations) and intelligent analysis (LLMs) makes Analysi Security effective at automating SOC analyst investigations.
