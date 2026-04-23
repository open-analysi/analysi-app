# Cy Language Type Checking

Complete reference for static type checking, type inference, integration tool validation, and the `analyze_types()` API.

## Overview

Cy provides **optional static type checking** at compile-time to catch errors before execution:

- **Off by default** - No performance overhead during development
- **Enable with `check_types=True`** - Get compile-time validation
- **Python type hints** - Tool signatures use standard Python typing
- **Integration tool validation** - Type-check tool calls against registered signatures

## When Type Checking Happens

Type checking occurs **during the `.run()` call**, not at a separate compilation step. When you call `.run()`, Cy processes your script in these phases:

1. **Parse** - Convert script text to Abstract Syntax Tree (AST)
2. **Type Check** - Validate types if `check_types=True` ← **Errors caught here!**
3. **Execute** - Run the script (only if type checking passed)

### With `check_types=True`

```python
cy = Cy(check_types=True)
result = cy.run(script, input_data)  # Type check happens HERE, before execution

# If type errors exist:
#   - Raises TypeError with all errors
#   - Execution NEVER starts
#   - No runtime errors from type mismatches!
```

This is **"compile-time" checking** - errors are caught before your script runs, not during execution.

### Without `check_types=True` (Default)

```python
cy = Cy()  # check_types=False by default
result = cy.run(script, input_data)  # Skips type checking

# Type checking is skipped:
#   - No type validation occurs
#   - Type errors may cause runtime failures
#   - Operations on nullable types may fail at runtime
```

**Key difference:** With type checking OFF, you only discover type errors when the problematic code actually executes. With type checking ON, errors are caught before execution starts.

## Enabling Type Checking

### Basic Usage

```python
from cy_language import Cy

# Type checking disabled (default)
cy = Cy()
result = cy.run(script, input_data)

# Type checking enabled - validates during .run() before execution
cy = Cy(check_types=True)
result = cy.run(script, input_data)  # Type check → then execute
```

### With Input Data (Schema Auto-Derived)

```python
from cy_language import Cy

cy = Cy(check_types=True)

# Schema is automatically derived from input_data structure
input_data = {
    "ip_address": "192.168.1.1",  # Inferred as string
    "port": 8080,                  # Inferred as number
    "active": True                 # Inferred as boolean
}

# Type checker automatically knows input field types
result = cy.run(script, input_data)
```

## What Gets Type Checked

Type checking validates:

1. **Arithmetic operations** - Operands must be numbers
2. **String operations** - Operands must be strings
3. **List operations** - Operands must be lists
4. **Dictionary field access** - Keys must exist in known structures
5. **Tool calls** - Arguments must match tool signatures
6. **Return types** - Must match declared or inferred types

### Type Checking Examples

#### Arithmetic Validation

```cy
# ✅ Valid - both numbers
x = 10
y = 5
result = x + y  # OK

# ❌ Type error - string + number
name = "Alice"
age = 30
invalid = name + age  # ERROR: Cannot add string and number
```

#### Dictionary Field Access

```cy
# With known structure
user = {"name": "Alice", "age": 30}
name = user.name      # ✅ OK - field exists
email = user.email    # ❌ ERROR - field doesn't exist

# With input data (schema auto-derived from input_data)
# Assuming input_data = {"ip_address": "192.168.1.1"}
ip = input.ip_address  # ✅ OK - field exists in input_data
port = input.port      # ❌ ERROR - field not in input_data
```

#### String Keys vs Variable Keys

```cy
# ✅ Literal string keys - type checked
data = {"name": "Alice", "age": 30}
name = data["name"]    # OK - key exists
invalid = data["email"]  # ERROR - key doesn't exist

# ⚠️ Variable keys - NOT type checked (runtime check)
key = "name"
value = data[key]  # Not validated at compile-time
```

**Why?** Type checker can only validate literal string keys at compile-time. Variable keys are checked at runtime.

## Type Inference

Cy automatically infers types from expressions:

```cy
# Number inference
count = 5              # Type: number
total = count + 10     # Type: number

# String inference
name = "Alice"         # Type: string
greeting = "Hello ${name}"  # Type: string

# List inference
items = [1, 2, 3]      # Type: list[number]
first = items[0]       # Type: number

# Dictionary inference
user = {"name": "Alice", "age": 30}  # Type: dict with known fields
name = user.name       # Type: string
age = user.age         # Type: number

# Conditional expression creates union type
flag = True
value = if (flag) { 42 } else { "text" }  # Type: number | string
```

## Error Messages

Type errors include location and helpful context:

```cy
# Script with type error
x = "hello"
y = x + 10

# Error message:
# Line 2, Col 9: Type error: Cannot add string and number
#   Left operand type: string
#   Right operand type: number
```

### Multiple Errors

Type checker collects ALL errors before failing:

```cy
# Script with multiple errors
name = "Alice"
age = "30"  # Should be number

result1 = name + 100    # ERROR 1
result2 = age - 5       # ERROR 2
data = {"x": 1}
value = data.missing    # ERROR 3

# All 3 errors reported together
```

## Truthy/Falsy Behavior (Python-like)

Type checking allows non-boolean values in conditions:

```cy
# Strings - empty is falsy
name = ""
if (name) {  # ✅ OK - empty string is falsy
    output = "Has name"
}

# Numbers - zero is falsy
count = 0
if (count) {  # ✅ OK - zero is falsy
    output = "Has items"
}

# Lists - empty is falsy
items = []
if (items) {  # ✅ OK - empty list is falsy
    output = "Has items"
}

# Explicit boolean check (more strict)
if (count > 0) {  # Better: explicit condition
    output = "Has items"
}
```

## Nullable Types and Safe Navigation

Field/array access returns nullable types `(type | null)` to prevent runtime null errors.
Operations on nullable types require the `??` (null-coalescing) operator.
**Philosophy**: Like Rust/TypeScript - "If it might be null, you MUST handle it explicitly."

### The `??` Operator

```cy
# Array/field access returns nullable
items = ["a", "b"]
first = items[0]        # Type: (string | null)
safe = first ?? ""      # Type: string (null removed!)

# Deep nesting - no defensive if-chains needed!
ip = alert.enrichments.network.source_ip ?? "0.0.0.0"  # One line!
# If ANY part missing → "0.0.0.0"

# Chaining for multiple fallbacks (try each in order)
city = user.address.billing.city ?? user.address.shipping.city ?? "Unknown"
target_ip = input.primary_ip ?? input.ioc_name ?? "1.1.1.1"
```

### Key Rules

**1. Indexed/field access is always nullable:**
```cy
items = ["a", "b", "c"]
first = items[0]   # Type: (string | null)
oob = items[10]    # Returns null at runtime (not an error)
email = user.email # Type: (Any | null) if field missing
```

**2. Operations require `??` operator:**
```cy
# ❌ Error
msg = "First: " + items[0]  # ERROR: nullable type

# ✅ Fix
msg = "First: " + (items[0] ?? "N/A")
```

**3. `??` vs `or` - important difference:**
```cy
count = data.count ?? 0    # 0 stays 0, null → 0 ✓
count = data.count or 0    # 0 → 0 (falsy) ✗
```

### String Interpolation

```cy
# ❌ Error
msg = "Uppercase: ${uppercase(items[0])}"  # Tool expects string, got nullable

# ✅ Fix
msg = "Uppercase: ${uppercase(items[0] ?? '')}"
```

### Workflow Safety

```cy
# Catches errors BEFORE deployment!
reputation = mcp::virustotal::ip_reputation(ip=input.ip)

# ❌ Compile error
is_malicious = reputation.score > 50  # ERROR: nullable

# ✅ Fix
safe_score = reputation.score ?? 0
is_malicious = safe_score > 50
```

### Special Cases

**`strict_input=True`** - trust input schema, get non-nullable types:
```py
analyze_types(script, input_schema=schema, strict_input=True)
# input.age returns number (not number | null)
```

**For-in loops** - variables are non-nullable:
```cy
for (item in items) {
    msg = "Item: " + item  # ✅ No ?? needed
}
```

### Common Errors

| Error | Fix |
|-------|-----|
| "Cannot add nullable type to string" | `msg = "First: " + (first ?? "N/A")` |
| "Cannot compare nullable types" | `safe_age = age ?? 0` then compare |
| "Tool parameter expects string, got nullable" | `uppercase(items[0] ?? "")` |

## Tool Type Validation

Integration tools can declare type signatures using Python type hints:

### Registering Tools with Type Hints

```python
from cy_language import Cy

def fetch_ip_reputation(ip_address: str, detailed: bool = False) -> dict:
    """Fetch IP reputation from VirusTotal."""
    return {
        "ip": ip_address,
        "malicious_score": 8,
        "reputation": "suspicious" if detailed else "bad"
    }

def calculate_risk_score(malicious_score: int, open_ports: int) -> int:
    """Calculate risk score from threat indicators."""
    return malicious_score * 10 + open_ports

tools = {
    "app::virustotal::ip_reputation": fetch_ip_reputation,
    "app::security::risk_score": calculate_risk_score
}

cy = Cy(check_types=True, tools=tools)
```

### Type-Safe Tool Calls

```cy
# ✅ Valid tool calls
vt_data = app::virustotal::ip_reputation(
    ip_address="8.8.8.8",
    detailed=True
)

risk = app::security::risk_score(
    malicious_score=8,
    open_ports=22
)

# ❌ Type errors caught at compile-time
bad1 = app::virustotal::ip_reputation(
    ip_address=123,  # ERROR: Expected string, got number
    detailed=True
)

bad2 = app::security::risk_score(
    malicious_score="high",  # ERROR: Expected int, got string
    open_ports=22
)
```

### Supported Python Type Hints

Cy type checker understands these Python types:

| Python Type | Cy Type | Example |
|-------------|---------|---------|
| `str` | `string` | `"hello"` |
| `int`, `float` | `number` | `42`, `3.14` |
| `bool` | `boolean` | `True`, `False` |
| `list` | `list` | `[1, 2, 3]` |
| `dict` | `dict` | `{"key": "value"}` |
| `List[str]` | `list[string]` | `["a", "b"]` |
| `Dict[str, int]` | `dict[string, number]` | `{"count": 5}` |

**Note:** Generic types like `List[T]` and `Dict[K, V]` require `from typing import List, Dict`.

## Static Analysis API

The `analyze_types()` function provides static analysis without execution:

### Basic Usage

```python
from cy_language import analyze_types

script = """
x = 10
y = 5
result = x + y
return result
"""

# Analyze without running (standalone function)
output_schema = analyze_types(code=script)

print(output_schema["symbol_table"])
# {
#   "x": {"type": "number"},
#   "y": {"type": "number"},
#   "result": {"type": "number"}
# }

print(output_schema["return_type"])
# {"type": "number"}
```

### With Input Schema (Static Analysis)

```python
from cy_language import analyze_types

script = """
ip = input.ip_address
score = input.malicious_score
risk = if (score > 7) { "HIGH" } else { "LOW" }
return {"ip": ip, "risk": risk}
"""

# Use standalone analyze_types function with explicit input_schema
output_schema = analyze_types(
    code=script,
    input_schema={
        "type": "object",
        "properties": {
            "ip_address": {"type": "string"},
            "malicious_score": {"type": "number"}
        }
    }
)

print(output_schema)
# {"type": "object", "properties": {
#   "ip": {"type": "string"},
#   "risk": {"type": "string"}
# }}
```

### With Integration Tools

```python
from cy_language import analyze_types

def virustotal_ip_reputation(ip_address: str) -> dict:
    return {"malicious_score": 8}

tool_registry = {
    "app::virustotal::ip_reputation": virustotal_ip_reputation
}

script = """
vt_data = app::virustotal::ip_reputation(ip_address="8.8.8.8")
score = vt_data.malicious_score
return score
"""

# Pass tools via tool_registry parameter
output_schema = analyze_types(code=script, tool_registry=tool_registry)

print(output_schema["symbol_table"])
# {
#   "vt_data": {"type": "dict"},
#   "score": {"type": "Any"}  # Field access on dict without known schema
# }
```

### Native Tools Included Automatically

**Important:** Native tools (len, sum, str, log, etc.) are **always available** in `analyze_types()`:

```python
from cy_language import analyze_types

# No need to register native tools!
script = """
items = [1, 2, 3]
count = len(items)
total = sum(items)
message = "Count: ${count}, Total: ${total}"
log(message)
return message
"""

# Native tools work automatically
output_schema = analyze_types(code=script)

print(output_schema["symbol_table"])
# {
#   "items": {"type": "list", "element_type": {"type": "number"}},
#   "count": {"type": "number"},
#   "total": {"type": "number"},
#   "message": {"type": "string"}
# }
```

### Analysis Result Structure

```python
{
    "symbol_table": {
        "variable_name": {"type": "...", ...},
        ...
    },
    "return_type": {"type": "...", ...},
    "errors": [...]  # Empty if no type errors
}
```

## When to Use Type Checking

### ✅ Use Type Checking When:

1. **Building production workflows** - Catch errors before deployment
2. **Working with external APIs** - Validate tool call parameters
3. **Complex data transformations** - Ensure type correctness
4. **Team collaboration** - Shared workflows benefit from type safety
5. **Integration development** - Validate integration tool usage

### ❌ Skip Type Checking When:

1. **Rapid prototyping** - Faster iteration without validation overhead
2. **One-off scripts** - Simple, immediate tasks
3. **Dynamic data exploration** - Unknown data structures
4. **Performance critical** - Avoid compile-time overhead (though minimal)

## Type Checking with Dynamic Data

### Known Structure (Type Checked)

```cy
# Structure defined in code - fully type checked
user = {
    "name": "Alice",
    "contact": {
        "email": "alice@example.com"
    }
}

email = user.contact.email  # ✅ Validated
```

### Unknown Structure (Runtime Checked)

```cy
# Data from external source - runtime checks
json_text = input.api_response
data = from_json(json_text)

# Type checker knows it's a dict, but not the fields
email = data.email  # ⚠️ Not validated at compile-time
```

### Hybrid Approach

```cy
# Validate structure, then use safely
json_text = input.api_response
data = from_json(json_text)

# Runtime validation
if (data.email == "") {
    return "Error: missing email"
}

# Now safe to use
email = data.email
return "Email: ${email}"
```

## Common Type Errors and Fixes

### Error: "Cannot add string and number"

```cy
# ❌ Wrong
name = "Alice"
age = 30
output = name + age  # ERROR

# ✅ Fix - convert to string
output = name + str(age)  # OK
output = "${name}${age}"   # OK - interpolation converts to string
```

### Error: "Field does not exist"

```cy
# ❌ Wrong
user = {"name": "Alice"}
email = user.email  # ERROR - field doesn't exist

# ✅ Fix - add field or use conditional
user = {"name": "Alice", "email": ""}  # Add field
# Or check existence at runtime
```

### Error: "Expected string, got number"

<!-- cy-test: expect-error -->
```cy
# ❌ Wrong — def is not valid Cy syntax
def process_text(text: str) -> str:
    return uppercase(text)
```

```cy
# ✅ Fix - pass correct type
result = app::custom::process_text(text="hello")  # OK
result = app::custom::process_text(text=str(42))  # OK - convert first
```

## Type Checking Best Practices

### ✅ Do This

- Enable type checking for production workflows
- Declare input schemas for better validation
- Use Python type hints for integration tools
- Use `analyze_types()` for static analysis
- Handle errors with try/catch for runtime safety
- Use string interpolation for type conversion

### ❌ Avoid This

- Don't rely on type checking for runtime validation
- Don't use variable keys when literal keys would work
- Don't ignore type errors - fix them
- Don't mix typed and untyped workflows

## Quick Reference

### Enabling Type Checking

```python
# Basic - schema auto-derived from input_data
cy = Cy(check_types=True)
result = cy.run(script, input_data)

# With tools
cy = Cy(
    check_types=True,
    tools={"app::tool::func": my_func}
)
result = cy.run(script, input_data)
```

### Static Analysis (Standalone Function)

```python
from cy_language import analyze_types

# Analyze types without running - standalone function
output_schema = analyze_types(
    code=script,
    input_schema={
        "type": "object",
        "properties": {"field": {"type": "string"}}
    }
)

# Raises TypeError if validation fails
print(f"Output type: {output_schema}")
```

### Type Hint Mapping

| Cy Type | Python Type Hint |
|---------|------------------|
| `string` | `str` |
| `number` | `int`, `float` |
| `boolean` | `bool` |
| `list` | `list`, `List[T]` |
| `dict` | `dict`, `Dict[K, V]` |
