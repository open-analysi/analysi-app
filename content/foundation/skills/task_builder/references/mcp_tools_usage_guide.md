# MCP Tools Usage Guide: Dos and Don'ts

## Overview

This guide documents practical findings from using the **analysi** MCP server tools. It captures real-world discoveries, gotchas, and best practices for task creation and validation.

## Key Discoveries

### 1. Three Ways to Call Integration Tools

#### Syntax 1: Fully Qualified `app::` prefix (Recommended)

```cy
domain = input.domain ?? "example.com"

# Fully qualified namespace prevents conflicts
vt_result = app::virustotal::domain_reputation(domain=domain)

return {
    "domain": domain,
    "virustotal_reputation": vt_result
}
```

**Benefits:**
- Explicit namespacing prevents tool name conflicts
- Clear which integration is being called
- Recommended for production code
- Works in both Task scripts and adhoc execution

#### Syntax 2: Unqualified Tool Name (Shorthand)

```cy
domain = input.domain ?? "example.com"

# Works as long as no other tools named "domain_reputation" exist
vt_result = domain_reputation(domain=domain)

return {
    "domain": domain,
    "virustotal_reputation": vt_result
}
```

**Use when:**
- Tool name is unique across all integrations
- Writing quick prototypes
- No naming conflicts in your environment

**Warning:** If multiple integrations have tools with the same name (e.g., both `virustotal` and `abuseipdb` have `ip_reputation`), you must use the fully qualified `app::` syntax to avoid ambiguity.

**Best Practice:** Always use the `app::` namespace syntax (Syntax 1) for clarity and consistency in both Task scripts and adhoc execution.

### 2. Return Statement Requirement

**All Cy scripts (tasks and adhoc) use `return` statements:**
✅ Correct syntax:
```cy
return {"result": "value"}
```

❌ **Common Mistake:**
```cy
# WRONG - Cy uses return, not output assignment
output = {"result": "value"}
# Error: "No return statement found in the program"
```

### 3. Validation Tools Behave Differently

#### `validate_cy_script` - Syntax Only (Fastest)

```json
{
  "script": "return {\"test\": \"hello\"}"
}
```

Returns:
- `valid`: true/false
- `errors`: syntax errors only
- **Does NOT check:** tool availability, integration names, parameter correctness, return statements

✅ **Use for:** Quick syntax checks before creating tasks (< 2ms)

#### `compile_script` - Full Validation with Integration Tools (**Recommended**)

```json
{
  "script": "result = app::virustotal::ip_reputation(ip=\"1.1.1.1\")\nreturn {\"result\": result}",
  "tenant": "default"
}
```

Returns:
```json
{
  "plan": {"compiled": true, "output_schema": {...}},
  "validation_errors": [],
  "tools_loaded": 15
}
```

**Features:**
- ✅ **Validates integration tool calls** (e.g., `app::virustotal::ip_reputation`)
- ✅ **Loads tool schemas from database** for tenant
- ✅ **Type inference** using Cy's analyze_types API
- ✅ Reports `tools_loaded` count to verify database access
- ⚠️ **Note:** Does NOT check for return statements (use validate_task_script for that)

**When to use:**
- **Before creating tasks** that use integration tools
- **Verify integration tool names** are correct
- **Check tool parameters** match expected schema
- **Replace old validate_task_script** for integration-based scripts

**Example - Integration tool validation:**
```json
// This will FAIL if "splunk" integration doesn't exist or "spl_run" action is invalid
{
  "script": "result = app::splunk::spl_run(query=\"index=main\")\nreturn {\"result\": result}",
  "tenant": "default"
}
// Returns: validation_errors: ["Tool 'app::splunk::spl_run' not found"] if missing
```

**Example - Built-in tools work without database:**
```json
// Works even with tenant parameter since built-in tools don't need database
{
  "script": "x = len([1, 2, 3])\nreturn {\"count\": x}",
  "tenant": "default"
}
// Returns: plan: {...}, validation_errors: [], tools_loaded: 0
```

#### `validate_task_script` - Task-Specific Validation (Legacy)

```json
{
  "script": "vt = call_action(\"virustotal\", \"ip_reputation\", {\"ip\": \"1.1.1.1\"})\noutput = vt"
}
```

Returns:
- `valid`: true/false
- `has_output`: true/false
- `errors`: includes return statement checks

⚠️ **Warning:** Does NOT validate integration tools. Use `compile_script` instead.

✅ **Use for:** Checking return statement presence only

**Recommendation:**
1. Use `validate_cy_script` for syntax (fast)
2. Use `compile_script` for integration tool validation (accurate)
3. Use `validate_task_script` only if you need return statement checking

## MCP Tool Reference

### Task Management

#### `create_task`

**Creates a new Task with validation.**

**Required Parameters:**
- `name` (string) - Human-readable task name
- `script` (string) - Cy script using `return {...}`
- `tenant` (string) - Tenant ID (usually "default")

**Important Optional Parameters:**
- `description` (string) - What the task does
- `function` (string) - Task function type (enrichment, reasoning, etc.)
- `scope` (string) - Pipeline position (input, processing, output)
- `categories` (list) - Tags for discovery
- `data_samples` (list) - **REQUIRED:** At least one sample input
- `authored_by` (string) - Creator identifier

**Example:**
```json
{
  "name": "Domain Reputation Enrichment",
  "script": "domain = input.domain ?? \"example.com\"\nvt_result = app::virustotal::domain_reputation(domain=domain)\nreturn {\"domain\": domain, \"reputation\": vt_result}",
  "tenant": "default",
  "description": "Enriches alerts with domain reputation from VirusTotal",
  "function": "enrichment",
  "scope": "processing",
  "categories": ["threat_intel", "domain"],
  "data_samples": [{"domain": "example.com"}],
  "authored_by": "security_team"
}
```

**Returns:**
```json
{
  "id": "uuid-here",
  "task": {
    "id": "uuid-here",
    "name": "Domain Reputation Enrichment",
    "cy_name": "domain_reputation_enrichment",
    "script": "...",
    "description": "..."
  }
}
```

**Common Errors:**

❌ **Missing data_samples:**
```json
{
  "error": "data_samples must be a non-empty list of sample inputs"
}
```

✅ **Fix:** Always provide at least one sample
```json
{
  "data_samples": [{"domain": "example.com"}]
}
```

❌ **Script without return statement:**
```json
{
  "error": "Script must contain 'return {...}' statement"
}
```

✅ **Fix:** Always end with return
```cy
return {"result": "value"}
```

#### `run_script`

**Test Cy scripts without creating a Task.**

**Parameters:**
- `script` (string) - Cy script using `return {...}` and `app::` syntax
- `input_data` (object, optional) - Test input data

**Example:**
```json
{
  "script": "domain = input[\"domain\"]\nvt = app::virustotal::domain_reputation(domain=domain)\nreturn {\"domain\": domain, \"reputation\": vt}",
  "input_data": {"domain": "google.com"}
}
```

**Returns:**
```json
{
  "task_run_id": "uuid",
  "status": "completed" | "failed",
  "output": "{...}",
  "error": null | "error message",
  "execution_time_ms": 790
}
```

**Best Practice:** Use adhoc execution to test integration calls before creating the task.

#### `get_task`

**Retrieve task details for one or more tasks by ID or cy_name.**

**Parameters:**
- `task_ids` (list of strings) - List of Task UUIDs or cy_names
- `tenant` (string) - Tenant ID

**Example:**
```json
{
  "task_ids": ["domain_reputation_enrichment"],
  "tenant": "default"
}
```

**Tip:** Use cy_name (not UUID) for better readability. You can request multiple tasks in a single call.

#### `list_tasks`

**List all tasks with optional filters.**

**Parameters:**
- `tenant` (string) - Tenant ID
- `function` (string, optional) - Filter by task function (e.g., "enrichment", "reasoning")
- `scope` (string, optional) - Filter by task scope (e.g., "processing", "input", "output")

**Example:**
```json
{
  "tenant": "default",
  "function": "enrichment"
}
```

**Returns:**
```json
{
  "tasks": [
    {
      "id": "uuid",
      "cy_name": "task_cy_name",
      "name": "Task Name",
      "description": "What this task does",
      "function": "enrichment",
      "scope": "processing"
    }
  ],
  "total": 4,
  "note": "Use get_task(task_ids=[...]) for full details including scripts"
}
```

### Integration Discovery

#### `list_integrations`

**List available integrations.**

**Parameters:**
- `configured_only` (boolean) - Only show configured integrations
- `tenant` (string) - Required when configured_only=true

**Example:**
```json
{
  "configured_only": true,
  "tenant": "default"
}
```

**Returns:**
```json
{
  "integrations": [
    {
      "integration_id": "splunk-local",
      "integration_type": "splunk",
      "name": "Splunk Production",
      "description": "...",
      "archetypes": ["SIEM"],
      "enabled": true
    },
    {
      "integration_id": "virustotal-main",
      "integration_type": "virustotal",
      "name": "VirusTotal",
      "description": "...",
      "archetypes": ["ThreatIntel"],
      "enabled": true
    }
  ],
  "count": 2,
  "filtered": true
}
```

**⚠️ CRITICAL: Understanding integration_id vs integration_type**

When `configured_only=true`, each integration has TWO important fields:

1. **`integration_id`**: The **instance name** (e.g., "splunk-local", "echo-edr-main", "virustotal-prod")
   - This is the unique name for THIS specific configured integration
   - Use this with `run_integration_tool()` to actually call the integration

2. **`integration_type`**: The **integration type** (e.g., "splunk", "echo_edr", "virustotal")
   - This identifies WHAT KIND of integration it is
   - Use this with `list_integration_tools()` to see available actions
   - Use this in Cy scripts: `app::splunk::search()` NOT `app::splunk-local::search()`

**Common Mistake:**
```cy
# ❌ WRONG - using integration_id (instance name) in Cy script
result = app::splunk-local::search(query="...")  # ERROR!

# ✅ CORRECT - using integration_type in Cy script
result = app::splunk::search(query="...")  # Works!
```

**Workflow:**
1. Use `list_integrations(configured_only=true)` to see configured instances
2. Note the `integration_type` field (e.g., "splunk", "virustotal")
3. Use `list_integration_tools(integration_type)` to see available actions
4. In Cy scripts, use `app::{integration_type}::{action}()` syntax

**Example:**
```json
// Step 1: List configured integrations
list_integrations(configured_only=true)
// Returns: {"integration_id": "splunk-local", "integration_type": "splunk", ...}

// Step 2: Get tools using integration_type (not integration_id!)
list_integration_tools("splunk")  // ✅ Correct - use "splunk"
// NOT: list_integration_tools("splunk-local")  // ❌ Wrong

// Step 3: In Cy script, use integration_type
app::splunk::search(query="...")  // ✅ Correct
```

**Best Practice:** Always use `configured_only: true` to see what's actually available in your environment.

#### `list_integration_tools`

**List available actions for an integration, with optional search filtering.**

**Parameters:**
- `integration_type` (string, optional) - Integration type (e.g., "virustotal", "splunk", "echo_edr")
- `query` (string, optional) - Search query to filter tools (e.g., "ip reputation")
- `category` (string, optional) - Filter by category (e.g., "threat_intel")

**Example:**
```json
{
  "integration_type": "virustotal"
}
```

**Returns:**
```json
{
  "integration_id": "virustotal",
  "tools": [
    {
      "action_id": "domain_reputation",
      "name": "Domain Reputation",
      "description": "Get reputation information for a domain",
      "parameters": {
        "domain": {
          "type": "string",
          "description": "Domain name to check",
          "required": true
        }
      },
      "cy_usage": "result = call_action(\"virustotal\", \"domain_reputation\", {\"domain\": \"<domain>\"})"
    }
  ]
}
```

**Tip:** Check `cy_usage` field for the exact syntax to use in your script.

## Workflow: Creating a Task End-to-End

### Step 1: Discover Available Integrations

```json
// MCP: list_integrations
{
  "configured_only": true,
  "tenant": "default"
}
```

**Result:** Find `virustotal` is available.

### Step 2: Check Available Actions

```json
// MCP: list_integration_tools
{
  "integration_id": "virustotal"
}
```

**Result:** Find `domain_reputation` action requires `domain` parameter.

### Step 3: Test Script with Adhoc Execution

```json
// MCP: run_script
{
  "script": "domain = input[\"domain\"]\nvt = app::virustotal::domain_reputation(domain=domain)\nreturn {\"domain\": domain, \"reputation\": vt}",
  "input_data": {"domain": "google.com"}
}
```

**Result:** Verify it returns reputation data successfully.

### Step 4: Validate Syntax

```json
// MCP: validate_cy_script
{
  "script": "domain = input.domain ?? \"example.com\"\n\nvt_result = app::virustotal::domain_reputation(domain=domain)\n\nreturn {\"domain\": domain, \"reputation\": vt_result}"
}
```

**Result:** `valid: true`

### Step 5: Create the Task

```json
// MCP: create_task
{
  "name": "Domain Reputation Enrichment",
  "script": "domain = input.domain ?? \"example.com\"\n\nvt_result = app::virustotal::domain_reputation(domain=domain)\n\nreturn {\"domain\": domain, \"virustotal_reputation\": vt_result}",
  "tenant": "default",
  "description": "Enriches alerts with domain reputation from VirusTotal",
  "function": "enrichment",
  "scope": "processing",
  "categories": ["threat_intel", "domain"],
  "data_samples": [{"domain": "example.com", "alert_id": "AL-001"}],
  "authored_by": "security_team"
}
```

**Result:** Task created with cy_name `domain_reputation_enrichment`

## Common Pitfalls and Solutions

### Pitfall 1: Tool Name Conflicts

❌ **Problem:**
```cy
# Multiple integrations have "ip_reputation" tool
# Which one will be called?
result = ip_reputation(ip="1.1.1.1")
# Could be virustotal.ip_reputation OR abuseipdb.ip_reputation!
```

✅ **Solution: Use fully qualified names**
```cy
# Explicit and unambiguous
vt_result = app::virustotal::ip_reputation(ip="1.1.1.1")
abuse_result = app::abuseipdb::ip_reputation(ip="1.1.1.1")
```

### Pitfall 2: Using Incorrect call_action Syntax

❌ **Wrong:**
```cy
# call_action is NOT valid Cy syntax
vt = call_action("virustotal", "domain_reputation", {"domain": domain})
return vt
# Error: Tool 'call_action' not found
```

✅ **Correct:**
```cy
# Use app:: namespace syntax
vt = app::virustotal::domain_reputation(domain=domain)
return vt
```

**Note:** The correct Cy syntax for calling integration tools is `app::integration_id::action_name(param=value)`. The `call_action()` function does not exist in Cy.

### Pitfall 3: Using `output` in Adhoc Scripts

❌ **Wrong:**
```cy
output = {"test": "hello"}
# Error: No return statement found
```

✅ **Correct:**
```cy
return {"test": "hello"}
```

### Pitfall 4: Forgetting data_samples

❌ **Wrong:**
```json
{
  "name": "My Task",
  "script": "return {...}",
  "tenant": "default"
  // Missing data_samples!
}
```

✅ **Correct:**
```json
{
  "name": "My Task",
  "script": "return {...}",
  "tenant": "default",
  "data_samples": [{"field": "value"}]
}
```

### Pitfall 5: data_samples Don't Match Script

❌ **Wrong:**
```cy
# Script expects "domain"
domain = input.domain ?? "example.com"
return {"domain": domain}
```

```json
// But data_samples provides "url" instead of "domain"
{
  "data_samples": [{"url": "example.com"}]
}
```

✅ **Correct:**
```json
// Match what script expects
{
  "data_samples": [{"domain": "example.com"}]
}
```

### Pitfall 6: Trusting `validate_task_script`

❌ **Problem:**
```json
// Returns false negative
{
  "valid": false,
  "errors": ["Tool 'call_action' not found"]
}
// But script is actually valid!
```

✅ **Solution:** Use `validate_cy_script` instead and verify output statement manually.

## Best Practices Summary

1. **Always test with adhoc first:** Use `run_script` to verify integration calls work
2. **Use `configured_only: true`:** When listing integrations to see what's actually available
3. **Provide realistic data_samples:** Match your script's expected input schema
4. **Check integration actions first:** Use `list_integration_tools` to see required parameters
5. **Prefer cy_name over UUIDs:** More readable and stable across environments
6. **Validate syntax, not task_script:** Use `validate_cy_script` for reliable syntax checking
7. **Document your script:** Add comments explaining what each integration call does
8. **Use descriptive names:** Task names should clearly indicate purpose

## Troubleshooting

### "No return statement found"

**Cause:** Using `output =` in adhoc execution.

**Fix:** Change to `return` for adhoc scripts.

### "Tool 'call_action' not found"

**Cause:** Using incorrect `call_action()` syntax (which does not exist in Cy).

**Fix:** Use `app::integration_id::action_name(param=value)` syntax instead. Example: `app::virustotal::ip_reputation(ip="8.8.8.8")`

### "data_samples must be a non-empty list"

**Cause:** Missing or empty data_samples field.

**Fix:** Add at least one sample: `"data_samples": [{"field": "value"}]`

### "Script must contain 'return {...}' statement"

**Cause:** Task script missing return statement.

**Fix:** Add `return {...}` at the end of your script.

### Integration returns null

**Cause:** Integration not configured or incorrect parameters.

**Fix:**
1. Verify integration is configured: `list_integrations(configured_only=true)`
2. Check parameter names: `list_integration_tools(integration_type)`
3. Test with known good data (e.g., "google.com" for domain reputation)

## See Also

- **task_validation_rules.md** - Complete validation requirements
- **integration_usage_guide.md** - Patterns for calling integrations
- **SKILL.md** - Task creation workflow and architecture
