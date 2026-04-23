# Integration Usage Guide

## Overview

This guide explains how to call external integrations from Cy scripts using the `app::` namespace syntax. For specific integration examples organized by category, see **integration_catalog.md**.

## Integration Call Syntax

```cy
result = app::integration_type::action_name(parameter=value, ...)
```

- **integration_type**: Integration type identifier (e.g., "virustotal", "splunk", "echo_edr")
  - ⚠️ Use the TYPE, not the instance name (e.g., "splunk" not "splunk-local")
- **action_name**: Specific action to execute (e.g., "ip_reputation", "search", "get_attributes")
- **parameters**: Named parameters specific to the action

**Example:**
```cy
# Call VirusTotal IP reputation with named parameter
vt_result = app::virustotal::ip_reputation(ip="185.220.101.45")
```

## ⚠️ CRITICAL: Cy-Boundary Shape vs MCP Shape (Read Before Writing `app::` Calls)

Design principle: `app::integration::action(...)` in Cy returns **what the action returns** — the business payload, nothing else. No envelope metadata to project around, no `status` to check, no `.data.` to dig through. Errors raise and fail the task cleanly.

This section documents how that principle is implemented so you can write scripts with confidence.

### The three shapes

**1. Action envelope (what the integration framework emits internally)**

Integrations return a dict with a `status` key. Two common shapes:

```json
// Flat shape (e.g., VirusTotal, AbuseIPDB, Splunk resolve_sourcetypes)
{"status": "success", "ip_address": "...", "reputation_summary": {...}, "network_info": {...}, ...}

// Wrapped shape (e.g., AD/LDAP run_query, Elasticsearch run_query)
{"status": "success", "data": <payload>, "summary": {...}, "message": "..."}

// Error (either shape can raise this)
{"status": "error", "error": "...", "error_type": "..."}
```

The `success_result(data=X)` helper in `integrations/framework/base.py` adds `timestamp`, `integration_id`, `action_id` on top. All of that is envelope metadata, not payload.

**2. MCP `run_integration_tool` response (what agents see when testing interactively)**

The MCP tool wraps the action envelope in its **own** envelope (`services/integration_execution_service.py`):

```json
{"status": "success" | "error" | "timeout", "output": <payload>, "output_schema": ..., "error": ..., "execution_time_ms": ...}
```

Agents testing via MCP see `status` at multiple levels. **That is an MCP concern, not a Cy concern. Do not carry it into your script.**

**3. Cy post-adapter shape (what `app::` actually returns to your script)**

`services/task_execution.py` rewrites dict results before handing them to Cy:

| Action envelope                                                              | What Cy sees                                                                                 |
|------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| `{"status": "error", "error": "...", ...}`                                    | **`RuntimeError` raised** — task fails cleanly                                               |
| `{"status": "success", "data": {k: v, ...}, "not_found": True, ...siblings}` | **Siblings merged into `data`** → flat dict `{not_found: True, k: v, ...}` (data keys win) |
| `{"status": "success", "data": [1,2,3]}` (list / scalar payload)             | Payload returned directly (`[1,2,3]`); siblings dropped (rare case)                          |
| `{"status": "success", ...flat fields...}` (flat, multi-field, no `data`)    | Flat dict minus envelope metadata                                                             |
| `{"status": "success", <one field>: V}` (legacy single-field, no `data`)     | `V` returned directly                                                                         |
| Non-dict result (list, string)                                              | Passed through unchanged                                                                      |

Concretely:
- **Errors are exceptions, not values.** Null checks and `.status == "error"` checks never fire. Let the exception propagate; only `try / catch` when you have a real fallback.
- **No envelope metadata reaches Cy.** `result.status`, `result.timestamp`, `result.integration_id`, `result.action_id` are all `null` — they were stripped.
- **`data` is unwrapped.** If the action returned `{status, data: {...}, ...siblings}`, Cy sees a single flat dict — `data`'s fields merged with siblings like `not_found`, `summary`, `message`. You never write `result.data.whatever`.
- **The `not_found=True` idiom works as expected.** For read actions (`lookup`, `get`, `search`, `query`), integrations return `success_result(not_found=True, data={...})` when the resource doesn't exist. In Cy, branch on `result.not_found`.

### Anti-pattern: dead status checks (REMOVE)

```cy
# ❌ DEAD CODE — `status` is stripped; errors would have raised before reaching this line
result = app::virustotal::ip_reputation(ip=ip)
if (result.status == "success") {         # always false → branch never taken
    verdict = result.malicious_votes
} else if (result.status == "error") {    # also unreachable — error would have raised
    verdict = "lookup_failed"
}
```

### Anti-pattern: projecting `.data` (REMOVE)

```cy
# ❌ OBSOLETE — the Cy boundary unwraps `data` automatically
user_result = app::ad_ldap::run_query(filter=f, attributes=a)
data_obj = user_result["data"] ?? {}          # `data` is gone — user_result IS the payload
entries = data_obj["entries"] ?? []
```

### Anti-pattern: null-check for error (REMOVE)

```cy
# ❌ BROKEN — errors raise, not return null
result = app::virustotal::ip_reputation(ip=ip)
if (result == null) { return {"error": "lookup failed"} }   # never triggers
```

### Correct patterns

**Default: call directly and let errors propagate** (this is the production norm — see `content/foundation/tasks/*.cy`)

```cy
# ✅ Flat-shape action — fields accessed directly
vt_report = app::virustotal::ip_reputation(ip=ip)
malicious = vt_report.reputation_summary.malicious ?? 0
# If the integration raises, the task fails cleanly — the workflow decides what to do next.
```

```cy
# ✅ Wrapped-shape action — Cy boundary already unwrapped `data` + merged siblings
user_result = app::ad_ldap::run_query(filter=ldap_filter, attributes="cn;memberOf")
entries = user_result.entries ?? []             # from data
total = user_result.total_objects ?? 0          # sibling from action
```

```cy
# ✅ not_found idiom — sibling flag reaches Cy as a top-level field
result = app::virustotal::ip_reputation(ip=ip)
if (result.not_found) {
    return enrich_alert(input, {"verdict": "no_intel_available"})
}
malicious = result.reputation_summary.malicious ?? 0
```

**Only use `try / catch` when you have a genuine fallback** (alternate data source, degraded-mode continuation)

```cy
# ✅ Justified: there's a real alternate path
try {
    data = app::virustotal::ip_reputation(ip=ip)
    source = "virustotal"
} catch (e) {
    data = app::abuseipdb::lookup_ip(ip=ip)
    source = "abuseipdb"
}
```

Don't reach for `try / catch` defensively — wrapping every `app::` call swallows real bugs and produces noisy scripts. If there's no fallback, let the task fail.

### Self-review checklist (run before shipping a Cy script)

1. Grep your script for `\.status\s*==` — if any hit after an `app::` call, **delete the branch** (both `== "success"` and `!= "success"` variants are dead code).
2. Grep for `\.data\.` or `\["data"\]` after any `app::` call — **remove the projection**; the Cy boundary already unwrapped the payload. Access fields one level up.
3. Grep for `== null` adjacent to `app::` calls — integration errors raise, they don't return null. Delete the check unless the field really is optional on a successful response.
4. If you tested the action via `run_integration_tool` and copied a `status` or `.output.data` path from the MCP response into Cy — remove it.
5. Only add `try / catch` around an `app::` call if the `catch` block does something other than return a synthetic failure record — a genuine fallback to another source, degraded-mode continuation, or batch accumulation of errors. Otherwise, let the task fail cleanly.

## Discovering Available Integrations

### ⚠️ CRITICAL: Integration Type vs Instance Name

When you run `list_integrations(configured_only=true)`, you'll see TWO fields for each integration:

**Example Response:**
```json
{
  "integration_id": "splunk-local",        // ← Instance name (don't use in Cy scripts!)
  "integration_type": "splunk",            // ← Type (use this in Cy scripts!)
  "name": "Splunk Production",
  "enabled": true
}
```

**Key Rules:**
1. **In Cy scripts**: Always use `integration_type` (e.g., "splunk", "virustotal", "echo_edr")
   ```cy
   ✅ result = app::splunk::search(query="...")        # Correct - using type
   ❌ result = app::splunk-local::search(query="...")  # Wrong - using instance name
   ```

2. **With `list_integration_tools()`**: Pass the `integration_type`
   ```
   ✅ list_integration_tools("splunk")        # Correct
   ❌ list_integration_tools("splunk-local")  # Wrong
   ```

3. **With `run_integration_tool()`**: Pass the `integration_id` (instance name)
   ```
   ✅ run_integration_tool("splunk-local", ...)  # Correct - needs specific instance
   ```

**Why the distinction?**
- Multiple teams might configure different Splunk instances ("splunk-prod", "splunk-dev")
- Your Cy script `app::splunk::search()` will use whichever instance is configured for your tenant
- You don't hardcode instance names in scripts - they're environment-specific

### List All Integrations

```json
// MCP tool: list_integrations
{
  "configured_only": true,
  "tenant": "default"
}
```

Returns list of integrations with:
- integration_id
- name
- description
- archetypes (ThreatIntel, SIEM, EDR, etc.)
- tool_count

### List Integration Tools

Use `list_integration_tools` to discover available actions. You can filter by integration type, search query, or category.

```json
// MCP tool: list_integration_tools — by integration type
{
  "integration_type": "virustotal"
}
// OR — by search query
{
  "query": "ip reputation"
}
// OR — by category
{
  "category": "threat_intel"
}
```

Returns matching actions with:
- action name
- parameters
- descriptions
- examples

**Search Patterns by Use Case:**

```
# Threat Intelligence
list_integration_tools(query="ip reputation")
list_integration_tools(query="domain reputation")
list_integration_tools(category="threat_intel")

# User/Asset Lookups
list_integration_tools(query="user lookup")
list_integration_tools(query="ldap active directory")

# SIEM Queries
list_integration_tools(query="search events")
list_integration_tools(integration_type="splunk")

# Ticketing
list_integration_tools(query="create ticket")
list_integration_tools(query="update issue")
```

**⚠️ Important:**
- `list_integration_tools` returns targeted results matching your query
- `list_integrations` returns all integrations (use `configured_only=true` to reduce context)
- **DO NOT use** `list_available_cy_tools` - returns 50K+ tokens! Use `list_integration_tools` instead

**After finding tools, get detailed actions:**
```
# Step 1: Search for relevant tools
list_integration_tools(query="ip reputation")
# Returns: virustotal, abuseipdb, alienvaultotx

# Step 2: Get detailed actions for selected integration
list_integration_tools(integration_type="virustotal")
```

## Multi-Integration Patterns

### Pattern 1: Parallel Enrichment

```cy
# Call multiple integrations in parallel
ip = input.ip ?? "8.8.8.8"

# Get reputation from multiple sources
vt_data = app::virustotal::ip_reputation(ip=ip)
abuse_data = app::abuseipdb::lookup_ip(ip=ip)
otx_data = app::alienvaultotx::ip_reputation(ip=ip)

# Aggregate results
return {
    "ip": ip,
    "reputation": {
        "virustotal": vt_data,
        "abuseipdb": abuse_data,
        "alienvault": otx_data
    }
}
```

### Pattern 2: Conditional Integration Calls

```cy
# Call integration based on condition
alert_type = input.type ?? "unknown"

if (alert_type == "phishing") {
    # URL-specific enrichment
    url = input.url ?? "http://example.com"
    url_data = app::urlscan::scan_url(url=url)
    return {"enrichment": url_data}
} elif (alert_type == "malware") {
    # File-specific enrichment
    file_hash = input.file_hash ?? ""
    vt_file = app::virustotal::file_reputation(file_hash=file_hash)
    return {"enrichment": vt_file}
} else {
    # Default IP enrichment
    ip = input.ip ?? "8.8.8.8"
    ip_data = app::virustotal::ip_reputation(ip=ip)
    return {"enrichment": ip_data}
}
```

### Pattern 3: Sequential with Dependency

```cy
# Second call depends on first call's result
username = input.username ?? "user@example.com"

# Step 1: Get user from AD
ad_data = app::ad_ldap::get_attributes(
    principals=username,
    attributes="mail"
)

# Step 2: Use email to query Okta
$email = ad_data["mail"]
okta_data = app::okta::list_users(
    filter='profile.email eq "${$email}"'
)

return {
    "username": username,
    "ad_data": ad_data,
    "okta_data": okta_data
}
```

## Combining Integration Data with LLM Reasoning

### CRITICAL: Always Use Alert Context

When using LLM to analyze integration results, **ALWAYS** include the alert context from the Alert Context Generator task to explain why we care about this analysis:

```cy
# Step 1: Extract alert context (from previous task)
alert_context = input.enrichments?.alert_context?.context_summary ??
                "No alert context available"

# Step 2: Call integration
ip = get_primary_observable_value(input) ?? "0.0.0.0"
vt_results = app::virustotal::ip_reputation(ip=ip)

# Step 3: Context-aware LLM analysis
analysis = llm_run(
    directive="""You are analyzing IP reputation for a security alert.

    ALERT CONTEXT: ${alert_context}

    Based on the alert context above, analyze this IP reputation data:
    1. Is this IP relevant to the alert described?
    2. Does the reputation align with the suspicious activity?
    3. What is the risk level specific to this context?

    Provide concise analysis (2-3 sentences) with specific evidence.
    """,
    data={
        "ip": ip,
        "reputation_data": vt_results
    }
)

# Step 4: Enrich with context-aware analysis
input.enrichments = input.enrichments ?? {}
input.enrichments.ip_reputation_analysis = {
    "ip": ip,
    "risk_assessment": analysis,
    "reputation_score": vt_results.malicious_votes ?? 0,
    "used_context": alert_context != "No alert context available"
}

return input
```

### Why Context Matters

Without context, the LLM can only provide generic analysis:
- ❌ "This IP has high malicious votes"
- ❌ "The reputation score is 95/100"

With context, the LLM provides relevant insights:
- ✅ "This Tor exit node aligns with the suspicious login attempt described in the alert"
- ✅ "The IP's malicious reputation (95/100) corroborates the credential stuffing attack pattern"

### Pattern: Multi-Integration Analysis with Context

```cy
# Get alert context
alert_context = input.enrichments?.alert_context?.context_summary ?? ""

# Gather data from multiple integrations
ip = get_primary_observable_value(input) ?? "0.0.0.0"
vt_data = app::virustotal::ip_reputation(ip=ip)
abuse_data = app::abuseipdb::check_ip(ip=ip)
shodan_data = app::shodan::ip_info(ip=ip)

# Synthesize with context-aware LLM
analysis = llm_run(
    directive="""Analyze threat intelligence findings for a security alert.

    ALERT CONTEXT: ${alert_context}

    Synthesize findings from multiple sources:
    - Determine relevance to the alert context
    - Identify consensus across sources
    - Assess overall risk in this specific scenario
    - Recommend action based on context + intel

    Be specific about how findings relate to the alert.
    """,
    data={
        "virustotal": vt_data,
        "abuseipdb": abuse_data,
        "shodan": shodan_data
    }
)

input.enrichments = input.enrichments ?? {}
input.enrichments.threat_intel_synthesis = analysis

return input
```

### Best Practices for Context-Aware Integration Tasks

1. **Always extract context first:**
   ```cy
   alert_context = input.enrichments?.alert_context?.context_summary ??
                   "No context available"
   ```

2. **Include context in every LLM directive:**
   ```cy
   directive = """Alert Context: ${alert_context}

   Now analyze the following integration data..."""
   ```

3. **Test with and without context:**
   ```json
   // Test sample with context
   {
     "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
     "enrichments": {
       "alert_context": {
         "context_summary": "Suspicious login from Tor exit node..."
       }
     }
   }

   // Test sample without context
   {
     "observables": [{"value": "8.8.8.8", "type": "IP Address"}],
     "enrichments": {}
   }
   ```

For comprehensive guidance on task dependencies and the Alert Context Pattern, see: `task_dependencies_pattern.md`

## Error Handling Best Practices

### Handle Missing Data

Integration **errors raise** — they do not return null. Use `??` for optional fields on a successful response and let real errors propagate. See "Cy-Boundary Shape" above.

```cy
# ✅ Production style — let errors propagate; `??` defaults for absent optional fields
ip = input.ip ?? "8.8.8.8"
ip_data = app::virustotal::ip_reputation(ip=ip)
response_code = ip_data.response_code ?? 0
if (response_code == 0) {
    return {"ip": ip, "reputation": "unknown", "note": "no data for this IP"}
}
return {"ip": ip, "reputation": ip_data}
```

### Provide Fallbacks

Only use `try / catch` when there's a real alternate data source or degraded path. This is the one case where catching the integration's exception is justified.

```cy
# ✅ Genuine fallback — primary integration errors, secondary picks up
ip = input.ip ?? "8.8.8.8"

try {
    vt_data = app::virustotal::ip_reputation(ip=ip)
    return {"ip": ip, "source": "virustotal", "data": vt_data}
} catch (e) {
    abuse_data = app::abuseipdb::lookup_ip(ip=ip, days=90)
    return {"ip": ip, "source": "abuseipdb", "data": abuse_data}
}
```

## Testing Integration Calls

### 1. Verify Integration is Configured

```json
// MCP tool: list_integrations
{
  "configured_only": true,
  "tenant": "default"
}
```

### 2. Check Available Actions

```json
// MCP tool: list_integration_tools
{
  "integration_type": "virustotal"
}
```

### 3. Test with Sample Data

```cy
# Start with hardcoded test data
test_ip = "8.8.8.8"
result = app::virustotal::ip_reputation(ip=test_ip)
return result
```

### 4. Handle Optional Response Fields

Integration errors RAISE — let them propagate. For optional fields on a successful response, use `??` defaults. See "Cy-Boundary Shape vs MCP Shape" above. Only wrap in `try / catch` if the task has a genuine fallback path.

```cy
ip = input.ip ?? "8.8.8.8"
result = app::virustotal::ip_reputation(ip=ip)
score = result.reputation_score ?? 0
return {"ip": ip, "score": score}
```

### 5. Test with Real Input

```cy
# Use actual input field
ip = input.source_ip ?? "8.8.8.8"
result = app::virustotal::ip_reputation(ip=ip)
return {"ip": ip, "reputation": result}
```

## Common Pitfalls

❌ **Don't hardcode credentials:**
```cy
# WRONG - credentials are managed externally
api_key = "abc123"
result = app::virustotal::ip_reputation(ip=ip, apikey=api_key)
```

✅ **Do let the platform handle auth:**
```cy
# CORRECT - platform injects credentials
result = app::virustotal::ip_reputation(ip=ip)
```

❌ **Don't ignore parameter requirements:**
```cy
# WRONG - missing required "ip" parameter
result = app::virustotal::ip_reputation()
```

✅ **Do check integration documentation:**
```cy
# CORRECT - provide all required parameters
ip = input.ip ?? "8.8.8.8"
result = app::virustotal::ip_reputation(ip=ip)
```

❌ **Don't check `.status` after an `app::` call:**
```cy
# WRONG - dead code: adapter strips `status` on success, raises on error
result = app::virustotal::ip_reputation(ip=ip)
if (result.status == "success") { ... }   # never entered
```

✅ **Do call directly and use `??` for optional response fields:**
```cy
# CORRECT — production style: let errors propagate, default optional fields
result = app::virustotal::ip_reputation(ip=ip)
score = result.reputation_score ?? 0
```

## Next Steps

For specific integration examples organized by category (Threat Intel, IAM, EDR, SIEM, etc.), see **integration_catalog.md**.
