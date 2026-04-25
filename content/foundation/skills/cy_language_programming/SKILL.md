---
name: cy-language-programming
description: Write and debug Cy language scripts for automation and workflow composition. Use when working with .cy files, Security Tasks, writing Cy programs, or debugging Cy syntax errors.
version: 1.1.0
---

# Cy Language Programming

Use this skill when the user is:
- Writing Cy language scripts (.cy files)
- Security Tasks are using Cy scripts
- Debugging Cy syntax or runtime errors
- Asking about Cy language features or syntax
- Building data processing workflows
- Working with type-safe workflow composition

## Quick Reference

### Core Syntax
- **Comments**: `#` (Python-style)
- **Variables**: `name = "Alice"` (no `$` prefix)
- **Strings**: `"single line"` or `"""multiline"""` with `${var}` interpolation
- **Booleans**: `True`, `False` (capitalized!)
- **Operators**: `and`, `or`, `not` (English words)
- **Required**: All code paths must `return`

**💡 IMPORTANT: Use `"""` for multiline strings (especially LLM prompts):**
```cy
# ✅ CORRECT - Use triple quotes for multiline
prompt = """Analyze this security alert:
Title: ${alert.title}
Severity: ${severity}

Provide a 2-sentence summary."""

result = llm_run(prompt=prompt)

# ❌ WRONG - Don't use string concatenation for multiline
prompt = "Analyze this security alert:\n" + "Title: " + alert.title + "\n..."
```

**⚠️ Cy is NOT object-oriented:** No methods/properties. Use functions, not `.method()` syntax.
- ❌ `text.length` → ✅ `len(text)`
- ❌ `text.split(",")` → ✅ `split(text, ",")`
- ❌ `items.push(x)` → ✅ `items = items + [x]`
- ❌ `items.map(fn)` → ✅ `[expr for(x in items)]` (list comprehension)
- **Note**: Dot (`.`) is ONLY for dict field access: `user.name` where `user = {"name": "Alice"}`

**⚠️ Common mistakes:** See Production Best Practices section below for detailed DO/DON'T rules.

### Common Patterns
```cy
# Basic structure
data = input.field
result = process(data)
return result
```

```cy
# Safe navigation with null-coalescing
# Field/array access returns nullable types - use ?? operator to handle nulls
# Philosophy: Like Rust/TypeScript - if it might be null, handle it explicitly

# Indexed/field access returns (type | null)
# List out-of-bounds returns null (same as dict missing key)
items = ["a", "b"]
first = items[0]        # Type: (string | null) - might be out of bounds
third = items[5]        # Returns null (not an error!)
name = user.email       # Type: (string | null) - field might not exist

# Operations on nullable types require ?? operator
msg = "First: " + first              # ERROR: can't add nullable to string
safe_msg = "First: " + (first ?? "") # OK: ?? removes null from type

# Type checking catches nullable errors at COMPILE TIME (not runtime!)
# With check_types=True or analyze_types(), you'll get clear errors like:
# "Cannot add nullable type (string | null) to string. Use ?? operator to handle null."
# This prevents null reference errors before your script ever runs!

# Deep field access with ?? — chain freely, missing intermediates return null
ip = alert.enrichments.network.source_ip ?? "0.0.0.0"

# More examples - just chain field access freely:
country = alert.enrichments.geo.country ?? "Unknown"
severity = alert.severity ?? "medium"
user_email = data.user.profile.contact.email ?? "no-email@example.com"
score = result.analysis.threat.score ?? 0

# Deep nesting? No problem! Missing intermediate fields return null
city = user.address.billing.city ?? user.address.shipping.city ?? "Unknown"

# ?? vs 'or' - Important distinction!
count = data.count ?? 0    # 0 stays 0, null becomes 0 ✓
count = data.count or 0    # 0 becomes 0 (0 is falsy) ✗
items = data.items ?? []   # [] stays [], null becomes [] ✓
items = data.items or []   # [] becomes [] ([] is falsy) ✗

# Safe navigation on primitives (runtime behavior)
# WITHOUT type checking: returns null for invalid field access
num = 42
field = num.some_field      # Returns null at runtime (not error)
# Works in interpolation too!
message = "Value: ${num.property}"  # "Value: null"

# WITH type checking (check_types=True): catches at compile time!
# The above would error: "cannot access field on number"

# ⚠️ IMPORTANT: Input field access with improved type inference (Cy 0.23+)
# When accessing input fields, ALWAYS use ?? operator for type safety!
# Without input schema, input.field returns (T | null) → becomes "unknown" type

# ❌ WRONG - causes type errors in 0.23+:
# text = input.description           # Type: unknown (no schema provided)
# summary = llm_summarize(text)      # ERROR: parameter expects string, got unknown

# ✅ CORRECT - use ?? for explicit type:
text = input.description ?? ""       # Type: string (inferred from default)
summary = llm_summarize(text)        # OK: parameter gets string type

# Works for all input patterns:
ip = input.ip ?? "192.168.1.100"     # string
count = input.count ?? 0              # number
data = input.alert ?? {}              # object
items = input.tags ?? []              # array

# This is the best practice for production scripts - always provide defaults!
```

```cy
# List comprehensions - concise transform/filter
ids = [u.id for(u in users)]                          # Extract field
admins = [u.name for(u in users) if(u.role == "admin")]  # With filter
doubled = [n * 2 for(n in nums)]                      # Transform
upper = [str::uppercase(w) for(w in words)]            # With tool calls
```

```cy
# For-in loops (for complex bodies or side effects)
for (item in items) {
    processed = transform(item)
    results = results + [processed]
}

# Dict iteration (iterates over KEYS like Python/JavaScript)
users = {"alice": 95, "bob": 87}
for (username in users) {
    score = users[username]
    results = results + ["${username}: ${score}"]
}
```

```cy
# Conditional expressions (ternary-like)
status = if (score >= 90) { "A" } else { "B" }
```

```cy
# Compound assignment operators (+=, -=, *=, /=, %=)
count = 10
count += 5     # count = count + 5
count *= 2     # count = count * 2
items = [1, 2]
items += [3]   # items = items + [3]
```

```cy
# Field assignment - syntactic sugar for dictionary assignment
# Field assignment — dot notation for dictionary fields
alert = {}
alert.severity = "high"           # Equivalent to: alert["severity"] = "high"
alert.enrichment.geo.country = "US"  # Auto-creates intermediate dicts!

# Works with compound operators too:
alert.count += 1               # Equivalent to: alert["count"] = alert["count"] + 1
alert.scores += [95]           # Appends to list

# Auto-create behavior (JavaScript-style):
data = {}
data.x.y.z = 5                 # Creates: {"x": {"y": {"z": 5}}}
# Missing fields and null values automatically become empty dicts

# Preserves existing fields when auto-creating:
config = {"x": {"existing": "value"}}
config.x.new_field = "data"    # config.x.existing still intact

# Mixed notation is NOT supported (parser limitation):
# obj.field["key"].value = x   # ❌ Syntax error
# Use consistent notation:
obj.field.key.value = x        # ✅ All dots
obj["field"]["key"]["value"] = x  # ✅ All brackets
```

```cy
# Error handling
try {
    data = risky_operation()
} catch (e) {
    log("Error: ${e}")
}
```

## Production Best Practices

Critical rules for writing production-ready Cy scripts:

### ✅ DO

- **Use `return` statement** - All scripts must end with `return`
- **Capitalize booleans** - Use `True` and `False` (capitalized)
- **Use English operators** - Use `and`, `or`, `not` (not symbols)
- **Use `${}` for interpolation** - Variables in strings: `"Hello ${name}"`
- **Assign without `$`** - Variables: `name = "value"` ($ only in interpolation)
- **Use `in` for containment** - `if (x in list)`, `if (substr in string)`, `if (key in dict)`
- **Use `range()` for numeric iteration** - `for (i in range(10)) { }` or `range(start, end, step?)`
- **Use list comprehensions** - `[x.name for(x in items) if(x.active)]` for transform/filter
- **Use `break`/`continue`** - For early exits and skipping iterations in loops
- **Always use `??` with input fields** - `input.field ?? "default"` (Cy 0.23+ type inference)
- **Use dot notation for dict fields** - `alert.severity = "high"` instead of `alert["severity"] = "high"`
- **Use elif** - `} elif (condition) {` (not "else if")

### ❌ DON'T

- **Lowercase booleans** - true/false → **Runtime error!**
- **Symbol operators** - && or || or ! → **Syntax error!**
- **Dollar sign outside interpolation** - $name = value → **Not allowed**
- **break/continue outside loops** - Only valid inside `for`/`while` → Compile error otherwise
- **Access input without `??`** - `input.field` → **Type error in 0.23+** (use `input.field ?? default`)
- **Semicolons** - `x = 5;` → Not needed
- **Assignment in conditions** - `if (x = 10)` → Use `==` for comparison
- **else if** - `} else if {` → Use `} elif {`
- **Missing function parens** - `length = len` → Use `len()`

### Common Workarounds

**Early loop exit with `break`:**
<!-- cy-test: compile-only -->
```cy
for (item in items) {
    if (condition) {
        break
    }
}
```

**Skip iterations with `continue`:**
<!-- cy-test: compile-only -->
```cy
for (item in items) {
    if (not valid) {
        continue
    }
    process(item)
}
```

**Numeric iteration:**
```cy
# Single-arg: range(end) — starts from 0
for (i in range(10)) {
    process(i)               # 0, 1, 2, ..., 9
}

# Two-arg: range(start, end)
for (i in range(5, 10)) {
    process(i)               # 5, 6, 7, 8, 9
}

# With step
for (i in range(0, 10, 2)) {
    log("Even: ${i}")        # 0, 2, 4, 6, 8
}
```

**Containment check with `in` operator:**
```cy
# Lists — membership test
if (2 in [1, 2, 3]) {
    log("found")
}

# Strings — substring test
if ("world" in "hello world") {
    log("contains it")
}

# Dicts — key lookup
if ("name" in {"name": "Alice", "age": 30}) {
    log("key exists")
}
```

## When to Load References

For detailed information, read the appropriate reference file:

**Syntax questions** → Read `reference/syntax-basics.md`
- Variables, strings, interpolation, data structures
- Common syntax mistakes and corrections

**Control flow** → Read `reference/control-flow.md`
- If/elif/else, for-in loops, while loops
- Conditional expressions, early returns

**Functions and tools** → Read `reference/functions-tools.md`
- Native functions (len, str, log, etc.)
- Namespace system (app::, arc::, mcp::)
- Tool registration and FQNs

**Type checking** → Read `reference/type-checking.md`
- Static type validation with `check_types=True`
- Type inference and `analyze_types()` standalone function
- Integration tool type safety
- Input schema auto-derivation

**Compiler API** → Read `reference/compiler-api.md`
- Python `Cy` class configuration and all parameters
- Automatic input schema derivation from input_data
- Tool registration with type hints
- Log capture with `captured_logs` parameter
- Error handling and performance tips
- Integration patterns (Flask, Celery, etc.)

**Advanced features** → Read `reference/advanced.md`
- Parallel execution
- Exception handling
- Complex workflows

## Native Functions (Always Available)

52 built-in functions (no imports needed):

**Original Functions (10):**
- `len(arg)` - Length of string/list/dict
- `sum(items)` - Sum numbers in list
- `str(value)` / `int(value)` - Type conversion
- `from_json(text)` / `to_json(data, indent?)` - JSON parsing/serialization
- `uppercase(text)` / `lowercase(text)` - Case conversion
- `join(items, sep?)` - Join list with separator
- `log(message)` - Log without affecting output

**Extended Functions (20):**
- **Type conversion**: `num(value)`, `bool(value)`
- **Time**: `now(timezone?)`
- **Iteration**: `range(end)` or `range(start, end, step?)`
- **String operations**: `split()`, `replace()`, `trim()`, `regex_match()`, `regex_extract()`
- **Array operations**: `reverse()`, `sort()`
- **Math operations**: `abs()`, `min()`, `max()`, `round()`
- **URL operations**: `url_encode()`, `url_decode()`
- **Dict operations**: `keys()`, `values()`

**Additional Functions (15):**
- **Time arithmetic**: `add_duration()`, `subtract_duration()`, `duration_between()`, `parse_duration()`, `format_duration()`, `timestamp_compare()`
- **Epoch conversion**: `from_epoch()`, `to_epoch()`
- **Network utilities**: `is_ipv4()`, `is_ipv6()`, `is_ip()`
- **String utilities**: `strip_markdown()`, `startswith()`, `endswith()`
- **List utilities**: `take()`
- For detailed time arithmetic documentation → See `reference/time-arithmetic.md`

**Collection & Utility Functions (7):**
- **Collections**: `unique(items)`, `flatten(items)`, `slice(items, start, end?)`, `index_of(items, value)`
- **Type introspection**: `type_of(value)` — returns "string", "number", "boolean", "list", "dict", or "null"
- **Encoding**: `base64_encode(text)`, `base64_decode(text)`

**See `reference/functions-tools.md` for detailed documentation and examples.**

## Common Runtime Errors

| Error | Cause | Fix |
|-------|-------|-----|
| **"Tool not found"** | Missing tool registration | Native functions auto-work; integration tools need registration |
| **"Cannot index NoneType"** | Accessing `input` without data | Provide `input_data` when executing |
| **Type errors at runtime** | Wrong types in operations | Enable `check_types=True` to catch at compile-time |

**For syntax errors** (booleans, operators, range, etc.) → See Production Best Practices section above.

## MCP Tools for Cy Development

Use these cy-script-assistant MCP tools when working with Cy code:

### Script Development & Testing

**`quick_syntax_check_cy_script(script)`** - Fast syntax validation
- Quick parse-only check (no type or symbol validation)
- Returns validation status and syntax errors
- Use for rapid feedback during development

**`compile_cy_script(script)`** - Full compilation with type checking
- Generates complete execution plan with node dependencies
- Validates tool calls and integration tool schemas
- Loads tenant-specific integration tool definitions
- Returns compilation errors, warnings, and execution plan
- Use before running scripts to catch all errors

**`get_plan_stats(script)`** - Analyze execution plan structure
- Returns node count, types, and execution statistics
- Useful for understanding parallelization opportunities
- Helps optimize complex workflows

**`execute_cy_script_adhoc(script, input_data?)`** - Test scripts quickly
- Execute Cy scripts without creating Task records
- Ideal for rapid prototyping and testing
- Optionally provide input_data for testing
- Returns output, errors, and execution time

### Tool & Integration Discovery

**`list_all_active_tool_summaries()`** - List all available tools
- Returns FQNs of native functions and integration tools
- Use for progressive disclosure (lightweight list)
- Follow up with `get_tool_details()` for specifics

**`get_tool_details(tool_fqns)`** - Get detailed tool information
- Fetch full schemas for selected tools
- Shows parameters, descriptions, types, and examples
- Use after browsing summaries to get implementation details

**`list_integrations(configured_only=True)`** - Browse integrations
- Lists available integrations with archetypes (ThreatIntel, AI, SIEM, etc.)
- Set `configured_only=True` to see only tenant-configured integrations
- Returns integration ID, name, description, and tool count

**`get_integration_tools(integration_id)`** - Get tools for an integration
- Shows all Cy-compatible tools for an integration
- Includes parameters, descriptions, and usage examples
- Use to discover available actions (e.g., "virustotal", "splunk")

**`search_integration_tools(query?, archetype?, category?)`** - Search for tools
- Search by query (name/description), archetype, or category
- Find tools across all integrations
- Useful for discovering tools by functionality

**`execute_integration_tool(integration_id, action_id, arguments, capture_schema?, timeout_seconds?)`** - Test integration tools
- Execute integration tools directly without writing Cy scripts
- Optionally capture JSON schema of output for schema discovery
- Returns status, output, optional schema, errors, and execution time
- Great for testing API calls before incorporating into workflows

### Schema & Data Models

Cy scripts receive and produce structured data (JSON dicts). The alert schema used at runtime depends on the deployment — Cy itself is schema-agnostic. Consult your project's alert schema skill (e.g., **ocsf-detection-finding**) for field names, enums, and mapping guidance.

### Task & Workflow Management

For creating/managing Tasks and Workflows, use the dedicated skills:
- **task-builder** skill - Create and manage Security Tasks
- **workflow-builder** skill - Build and manage Security Workflows

## Examples

### Learning Examples (`examples/`)

**`basic-processing.cy`** - JSON data transformation with native functions
- Demonstrates: JSON parsing, for-in loops, list/dict operations
- Uses: `from_json()`, `to_json()`, `len()`, `sum()`, `uppercase()`, `join()`
- Pattern: Parse input → Transform data → Calculate statistics → Return JSON
- Great for: Learning core Cy syntax and native function usage

**`api-workflow.cy`** - Parallel API calls with error handling
- Demonstrates: Parallel execution, try/catch, error aggregation
- Uses: for-in loops for parallelization, integration tools
- Pattern: Multiple independent API calls → Collect results + errors → Statistics
- Great for: Building resilient multi-API workflows

**`security-analysis.cy`** - Multi-source threat intelligence correlation
- Demonstrates: Complex conditional logic, risk scoring, multi-tool integration
- Uses: VirusTotal, Shodan, GeoIP integrations with parallel data gathering
- Pattern: Gather intel (parallel) → Calculate risk scores → Determine action
- Great for: Security workflows with multiple threat intelligence sources

**`type-safe-workflow.cy`** - Type-checked workflow with validation
- Demonstrates: Type checking, input schemas, typed tool calls
- Uses: Python type hints, compile-time validation, type inference
- Pattern: Typed input → Type-checked operations → Validated output
- Great for: Production workflows requiring type safety

**`bubble-sort.cy`** - Classic sorting algorithm implementation
- Demonstrates: Nested while loops, array rebuilding pattern, early exit with flags
- Uses: Array operations, conditional logic, loop control patterns
- Pattern: Iterative comparison → Array reconstruction → Optimization with flags
- Great for: Understanding algorithmic implementations and array manipulation in Cy

### Real-World Production Tasks

Use `mcp__cy-script-assistant__get_task()` to retrieve these examples:

**VirusTotal IP Reputation Analysis** (task: "VirusTotal: IP Reputation Analysis")
- Full-featured IP reputation workflow with LLM reasoning
- Demonstrates: App tool integration, complex conditionals, structured output
- **Pattern**: Threat intel → Risk calculation → LLM analysis → Recommendation

**Multi-Source IP Correlation** (task: "Multi-Source IP Reputation Correlation")
- Combines VirusTotal + AbuseIPDB for comprehensive assessment
- Demonstrates: Parallel data gathering, consensus building, discrepancy detection
- **Pattern**: Multiple sources (parallel) → Correlation → Consensus → Action

**Echo EDR Behavioral Analysis** (task: "Echo EDR: Comprehensive Behavioral Analysis")
- Unified endpoint analysis from multiple EDR data sources
- Demonstrates: Parallel data gathering, artifact storage, behavioral correlation
- **Pattern**: Pull all EDR data (parallel) → LLM correlation → Risk assessment

**Incident Response Orchestrator** (task: "Incident Response Orchestrator")
- Complete incident response workflow with team assignment and SLA tracking
- Demonstrates: Complex decision trees, team composition, escalation logic
- **Pattern**: Assess incident → Assign resources → Generate action plan → Communications

**AD LDAP Privileged User Check** (task: "AD LDAP: Privileged User Group Membership Check")
- Analyzes AD group memberships for privileged access detection
- Demonstrates: LDAP queries, LLM-powered privilege analysis, risk scoring
- **Pattern**: LDAP query → Group analysis → Privilege calculation → Risk assessment

**Splunk Event Retrieval** (task: "Splunk: Triggering Event Retrieval with SPL Generation and LLM Summarization")
- Generates SPL queries and retrieves/summarizes Splunk events
- Demonstrates: Dynamic query generation, conditional logic, artifact storage
- **Pattern**: Generate SPL → Execute query → Store artifacts → LLM summary

**Alert Disposition Flow** (tasks: "Alert Detailed Analysis" → "Alert Disposition Determination" → "Alert Summary Generation")
- Multi-task workflow for security alert triage
- Demonstrates: Workflow composition, LLM reasoning chain, artifact tracking
- **Pattern**: Analyze → Determine disposition → Generate summary → Store artifacts

## Templates

Use templates from `templates/` for quick starts:

**`basic-script.cy`** - Standard script structure
- Copy-paste starting point for new workflows
- Includes comments explaining key concepts
- Shows proper input handling and return patterns

**`typed-workflow.cy`** - Type-safe workflow template
- Includes Python setup code for type checking
- Shows how to define input schemas and tool signatures
- Best practice patterns for production workflows
