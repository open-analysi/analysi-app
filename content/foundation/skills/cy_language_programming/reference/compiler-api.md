# Cy Compiler API Reference

Complete guide to using the Cy compiler from Python - installation, configuration, tool registration, and execution.

## Installation

```bash
# Install from PyPI
pip install cy-language

# Or with Poetry
poetry add cy-language
```

## Basic Usage

### Minimal Example

```python
from cy_language import Cy

# Create compiler instance
cy = Cy()

# Write Cy script
script = """
name = "Alice"
greeting = "Hello ${name}!"
return greeting
"""

# Run script
result = cy.run(script)
print(result)  # "Hello Alice!"
```

### With Input Data

```python
from cy_language import Cy

cy = Cy()

script = """
name = input.name
age = input.age
return "User ${name} is ${age} years old"
"""

input_data = {"name": "Alice", "age": 30}
result = cy.run(script, input_data)
print(result)  # "User Alice is 30 years old"
```

## The Cy Class

### Constructor Options

```python
from cy_language import Cy

cy = Cy(
    tools=None,                     # Register custom tools
    variables=None,                 # Inject variables into program
    interpolation_mode="markdown",  # Interpolation mode (markdown, csv, xml)
    item_tag="item",                # XML tag name for list items
    mcp_servers=None,               # MCP server configurations (deprecated)
    enable_parallel=False,          # Enable parallel execution
    parallel_threshold=2,           # Min operations for parallelization
    captured_logs=None,             # List to capture log() output
    validate_output=True,           # Validate return/output statements
    check_types=False               # Enable compile-time type checking
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tools` | `dict` | `None` | Custom tool registry (FQN → function) |
| `variables` | `dict` | `None` | Variables to inject into program scope |
| `interpolation_mode` | `str` | `"markdown"` | Default interpolation mode for lists |
| `item_tag` | `str` | `"item"` | XML tag name for items when mode="xml" |
| `mcp_servers` | `dict` | `None` | MCP server configurations (deprecated - use async) |
| `enable_parallel` | `bool` | `False` | Enable parallel execution of for-in loops |
| `parallel_threshold` | `int` | `2` | Minimum operations to trigger parallelization |
| `captured_logs` | `list` | `None` | List to capture `log()` output (None → stderr) |
| `validate_output` | `bool` | `True` | Validate all code paths have return statement |
| `check_types` | `bool` | `False` | Enable compile-time type checking |

**Important Note:** Input schemas are **automatically derived** from `input_data` when `check_types=True`. You don't need to specify them separately.

### Methods

#### `run(script, input_data=None)`

Execute a Cy script and return the result:

```python
result = cy.run(script, input_data={"field": "value"})
```

**Parameters:**
- `script` (str): Cy script source code
- `input_data` (dict, optional): Input data accessible via `input` variable

**Returns:** Result of the script's `return` statement

**Raises:**
- `CyParseError`: Syntax errors in script
- `CyTypeError`: Type errors (if `check_types=True`)
- `CyRuntimeError`: Runtime execution errors

**Note:** For static type analysis, use the standalone `analyze_types()` function (documented in "Static Analysis API" section below), not a method on the `Cy` class.

## Async MCP Integration

For Model Context Protocol (MCP) integration, use the async factory method `Cy.create_async()` instead of the regular constructor:

```python
from cy_language import Cy

async def main():
    # Create Cy instance with MCP servers
    cy = await Cy.create_async(
        mcp_servers={
            "demo": {
                "base_url": "http://localhost:8000",
                "mcp_id": "demo"
            },
            "virustotal": {
                "base_url": "http://virustotal-mcp:8001",
                "mcp_id": "virustotal"
            }
        },
        tools=my_tools,           # Can combine with regular tools
        check_types=True          # All regular parameters work
    )

    # MCP-enabled script
    script = """
    # MCP tools use mcp:: namespace
    result = mcp::demo::add(a=10, b=20)
    vt_data = mcp::virustotal::ip_reputation(ip="8.8.8.8")

    return {"sum": result, "reputation": vt_data}
    """

    # Run with async
    output = await cy.run_async(script)
    print(output)

import asyncio
asyncio.run(main())
```

**Key Points:**
- Use `await Cy.create_async(mcp_servers={...})` for MCP support
- Run scripts with `await cy.run_async(script, input_data)`
- MCP tools use `mcp::server_name::tool_name()` syntax
- All regular `Cy()` parameters work with `create_async()`
- The `mcp_servers` parameter on `Cy()` is deprecated (raises error)

## Type Checking with Input Data

When `check_types=True`, input schemas are **automatically derived** from the `input_data` you provide:

### Automatic Schema Derivation

```python
from cy_language import Cy

cy = Cy(check_types=True)  # No input_schema parameter needed!

script = """
ip = input.ip_address      # Type: string (auto-inferred)
port = input.port          # Type: number (auto-inferred)
active = input.active      # Type: boolean (auto-inferred)
return "Connecting to ${ip}:${port}"
"""

# Schema is automatically derived from this input_data
result = cy.run(script, {
    "ip_address": "192.168.1.1",  # Inferred as string
    "port": 8080,                  # Inferred as number
    "active": True                 # Inferred as boolean
})
```

### With Nested Data

```python
cy = Cy(check_types=True)

script = """
name = input.user.name
email = input.user.contact.email
return "Contact: ${name} at ${email}"
"""

# Nested structure is auto-inferred
result = cy.run(script, {
    "user": {
        "name": "Alice",
        "age": 30,
        "contact": {
            "email": "alice@example.com",
            "phone": "555-1234"
        }
    },
    "tags": ["vip", "verified"]
})
```

### Supported Schema Types

| Schema Type | Cy Type | Example |
|-------------|---------|---------|
| `"string"` | string | `"hello"` |
| `"number"` | number | `42`, `3.14` |
| `"boolean"` | boolean | `True`, `False` |
| `"list"` | list | `[1, 2, 3]` |
| `"dict"` | dict | `{"key": "value"}` |
| `{"field": "type"}` | dict with known fields | Nested object |

## Registering Tools

### Basic Tool Registration

```python
from cy_language import Cy

def greet(name: str, greeting: str = "Hello") -> str:
    """Greet a user with a custom greeting."""
    return f"{greeting}, {name}!"

tools = {
    "app::custom::greet": greet
}

cy = Cy(tools=tools)

script = """
message = app::custom::greet(name="Alice", greeting="Hi")
return message
"""

result = cy.run(script)  # "Hi, Alice!"
```

### Multiple Tools

```python
def calculate_risk(malicious_score: int, open_ports: int) -> int:
    """Calculate risk score from indicators."""
    return malicious_score * 10 + open_ports

def format_report(ip: str, risk_score: int) -> dict:
    """Format security report."""
    return {
        "ip": ip,
        "risk_score": risk_score,
        "severity": "HIGH" if risk_score > 70 else "LOW"
    }

tools = {
    "app::security::calculate_risk": calculate_risk,
    "app::security::format_report": format_report
}

cy = Cy(check_types=True, tools=tools)

script = """
risk = app::security::calculate_risk(malicious_score=8, open_ports=22)
report = app::security::format_report(ip="8.8.8.8", risk_score=risk)
return report
"""
```

### Tool Naming Convention (FQN)

Tools use Fully Qualified Names with namespace prefixes:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `native::tools::` | Built-in functions | `native::tools::len` |
| `app::` | Your application tools | `app::virustotal::ip_reputation` |
| `arc::` | Archetype tools | `arc::processor::transform` |
| `mcp::` | MCP protocol tools | `mcp::demo::add` |

**Best practice:** Always use `app::category::function_name` format for custom tools.

## Type Checking Configuration

### Enabling Type Checking

```python
from cy_language import Cy

# Type checking disabled (default) - faster development
cy_dev = Cy(check_types=False)

# Type checking enabled - production validation
cy_prod = Cy(check_types=True)
```

### With Tools and Type Hints

```python
def fetch_data(url: str, timeout: int = 30) -> dict:
    """Fetch data from URL with timeout."""
    # Implementation...
    return {"status": "ok", "data": {...}}

tools = {
    "app::http::fetch": fetch_data
}

cy = Cy(check_types=True, tools=tools)

script = """
# ✅ Valid - types match
response = app::http::fetch(url="api.com/data", timeout=10)

# ❌ Type error - caught at compile-time
bad = app::http::fetch(url=123, timeout="slow")
"""

# This will raise CyTypeError before execution
result = cy.run(script)
```

### Type Checking Best Practices

```python
# ✅ Development - fast iteration, no validation
cy_dev = Cy(check_types=False)

# ✅ Testing - validate types before deployment
cy_test = Cy(
    check_types=True,
    input_schema=test_schema,
    tools=test_tools
)

# ✅ Production - full validation with schema
cy_prod = Cy(
    check_types=True,
    input_schema=production_schema,
    tools=production_tools
)
```

## Error Handling

### Catching Execution Errors

```python
from cy_language import Cy, CyRuntimeError, CyTypeError, CyParseError

cy = Cy(check_types=True)

script = """
x = 10 / 0  # Division by zero
return x
"""

try:
    result = cy.run(script)
except CyParseError as e:
    print(f"Syntax error: {e}")
except CyTypeError as e:
    print(f"Type error: {e}")
except CyRuntimeError as e:
    print(f"Runtime error: {e}")
```

### Error Types

| Exception | When Raised | Example |
|-----------|-------------|---------|
| `CyParseError` | Syntax errors in script | Missing brace, invalid token |
| `CyTypeError` | Type validation fails | Wrong argument type |
| `CyRuntimeError` | Execution errors | Division by zero, undefined variable |

### Validating Input Data

```python
from cy_language import Cy

cy = Cy(check_types=True)

script = """
ip = input.ip_address
port = input.port
return "Connecting to ${ip}:${port}"
"""

# ❌ This will cause runtime error - missing required field
# Schema is auto-derived, so it expects both fields
try:
    result = cy.run(script, {"ip_address": "192.168.1.1"})
    # Missing "port" field - validation will fail
except CyRuntimeError as e:
    print(f"Missing input field: {e}")

# ✅ Valid input data - schema auto-derived from this
result = cy.run(script, {
    "ip_address": "192.168.1.1",
    "port": 8080
})
```

## Capturing Log Output

The `log()` function outputs to stderr by default, but you can capture logs programmatically using the `captured_logs` parameter:

### Basic Log Capture

```python
from cy_language import Cy

# Create a list to capture logs
logs = []
cy = Cy(captured_logs=logs)

script = """
log("Processing started")
items = ["apple", "banana", "cherry"]
log("Found ${len(items)} items")

for (item in items) {
    log("Processing: ${item}")
}

log("Processing complete")
return "Done"
"""

result = cy.run(script)

# Check captured logs
print(f"Result: {result}")
print(f"Logs captured: {len(logs)}")
for log_msg in logs:
    print(f"  - {log_msg}")

# Output:
# Result: Done
# Logs captured: 6
#   - Processing started
#   - Found 3 items
#   - Processing: apple
#   - Processing: banana
#   - Processing: cherry
#   - Processing complete
```

### Log Capture for Debugging

```python
from cy_language import Cy

def debug_script(script: str, input_data: dict = None):
    """Run script with log capture for debugging."""
    logs = []
    cy = Cy(captured_logs=logs)

    try:
        result = cy.run(script, input_data)
        print(f"✅ Success: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Print all logs for debugging
    if logs:
        print(f"\n📋 Execution Logs ({len(logs)} entries):")
        for i, log_msg in enumerate(logs, 1):
            print(f"  {i}. {log_msg}")

# Usage
script = """
log("Starting calculation")
x = input.value
log("Input value: ${x}")
result = x * 2
log("Result: ${result}")
return result
"""

debug_script(script, {"value": 42})
```

### Log Capture in Production

```python
from cy_language import Cy
import json

class WorkflowEngine:
    def execute_with_audit(self, script: str, input_data: dict) -> dict:
        """Execute workflow and capture audit logs."""
        logs = []
        cy = Cy(
            check_types=True,
            tools=self.tools,
            captured_logs=logs
        )

        try:
            result = cy.run(script, input_data)

            return {
                "status": "success",
                "result": result,
                "audit_logs": logs,
                "log_count": len(logs)
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "audit_logs": logs,
                "log_count": len(logs)
            }

# Usage
engine = WorkflowEngine()
outcome = engine.execute_with_audit(script, input_data)

# Store audit trail
with open("audit_trail.json", "w") as f:
    json.dump(outcome, f, indent=2)
```

### Without Log Capture (Default Behavior)

```python
from cy_language import Cy

# Logs go to stderr (default)
cy = Cy()

script = """
log("This goes to stderr")
return "Result"
"""

result = cy.run(script)
# Log output appears in terminal/console
# Only the return value is captured
```

**Key Points:**
- Pass `captured_logs=[]` to capture logs in a list
- Without `captured_logs`, logs go to stderr
- Logs don't affect the return value
- Useful for debugging, audit trails, and monitoring
- Each `log()` call adds one string to the list

## Static Analysis API

The `analyze_types()` function is a **standalone function** (not a method on `Cy` class) that performs static type analysis without executing code.

### Basic Analysis

```python
from cy_language import analyze_types

script = """
items = [1, 2, 3, 4, 5]
count = len(items)
total = sum(items)
average = total / count
return average
"""

# analyze_types is a standalone function
output_schema = analyze_types(script)

print(f"Output type: {output_schema['type']}")
# Output type: number
```

### Analysis with Input Schema

```python
from cy_language import analyze_types

script = """
name = input.name
age = input.age
return "User ${name} is ${age} years old"
"""

# Provide explicit input schema for validation
output_schema = analyze_types(
    code=script,
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "number"}
        }
    }
)

print(output_schema)
# {"type": "string"}
```

### Pre-deployment Validation

```python
from cy_language import analyze_types

def validate_workflow(script: str, input_schema: dict = None) -> bool:
    """Validate workflow before deployment using static analysis."""
    try:
        # Use standalone analyze_types function
        output_schema = analyze_types(
            code=script,
            input_schema=input_schema,
            strict_input=True  # Strict validation for production
        )

        print("✅ Workflow is type-safe!")
        print(f"Output type: {output_schema}")
        return True

    except TypeError as e:
        print("❌ Type errors found:")
        print(f"  {e}")
        return False
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False

# Usage
input_schema = {
    "type": "object",
    "properties": {
        "ip_address": {"type": "string"},
        "context": {"type": "string"}
    }
}

is_valid = validate_workflow(my_script, input_schema)
```

### Tool Registry for Static Analysis

```python
from cy_language import analyze_types
from cy_language.tool_registry_builder import build_tool_registry, export_custom_tools

# Build tool registry with type information
def virustotal_ip_reputation(ip_address: str) -> dict:
    """Check IP reputation."""
    pass

def calculate_risk(malicious_score: int, open_ports: int) -> int:
    """Calculate risk score."""
    pass

# Create tool registry
tools = {
    "app::virustotal::ip_reputation": virustotal_ip_reputation,
    "app::security::calculate_risk": calculate_risk
}

tool_registry = export_custom_tools(tools)

script = """
ip = input.ip_address
vt_data = app::virustotal::ip_reputation(ip_address=ip)
risk = app::security::calculate_risk(
    malicious_score=vt_data.malicious_score,
    open_ports=22
)
return risk
"""

# Analyze with tool registry
output_schema = analyze_types(
    code=script,
    tool_registry=tool_registry.to_dict(),
    input_schema={
        "type": "object",
        "properties": {"ip_address": {"type": "string"}}
    }
)

print(f"Output: {output_schema}")
# {"type": "number"}
```

## Integration Patterns

### Flask/FastAPI Integration

```python
from flask import Flask, request, jsonify
from cy_language import Cy, CyRuntimeError

app = Flask(__name__)

# Initialize Cy compiler with tools
cy = Cy(
    check_types=True,
    tools=security_tools,
    input_schema={"ip_address": "string"}
)

@app.route("/analyze", methods=["POST"])
def analyze_ip():
    try:
        # Load script from database/file
        script = load_workflow_script("ip_analysis")

        # Get input from request
        input_data = request.json

        # Execute workflow
        result = cy.run(script, input_data)

        return jsonify({"status": "success", "result": result})

    except CyRuntimeError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
```

### Celery Task Integration

```python
from celery import Celery
from cy_language import Cy

celery_app = Celery("tasks")

@celery_app.task
def run_security_analysis(script: str, input_data: dict):
    """Execute Cy workflow as async task."""
    cy = Cy(
        check_types=True,
        tools=get_security_tools()
    )

    result = cy.run(script, input_data)
    return result

# Usage
task = run_security_analysis.delay(
    script=workflow_script,
    input_data={"ip": "8.8.8.8"}
)
result = task.get()
```

### Multi-tenant Tool Isolation

```python
from cy_language import Cy

class WorkflowEngine:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.tools = self._load_tenant_tools(tenant_id)
        self.cy = Cy(check_types=True, tools=self.tools)

    def _load_tenant_tools(self, tenant_id: str) -> dict:
        """Load tools specific to tenant."""
        # Load from database, filter by tenant
        return {...}

    def execute(self, script: str, input_data: dict):
        """Execute workflow with tenant-specific tools."""
        return self.cy.run(script, input_data)

# Usage
tenant_a = WorkflowEngine("tenant_a")
tenant_b = WorkflowEngine("tenant_b")

result_a = tenant_a.execute(script, input_a)
result_b = tenant_b.execute(script, input_b)
```

## Performance Considerations

### Reusing Cy Instance

```python
# ✅ Good - reuse instance
cy = Cy(check_types=True, tools=tools)

for script in scripts:
    result = cy.run(script, input_data)
    process(result)

# ❌ Bad - creating new instance each time
for script in scripts:
    cy = Cy(check_types=True, tools=tools)  # Expensive!
    result = cy.run(script, input_data)
```

### Type Checking Overhead

```python
# Development - disable type checking for speed
cy_dev = Cy(check_types=False)

# Production - enable after validation
cy_prod = Cy(check_types=True)

# Best practice: validate once, then disable for execution
script = load_script()

# Validate during deployment
cy_validator = Cy(check_types=True, tools=tools)
analysis = cy_validator.analyze_types(script)

if analysis["errors"]:
    raise ValueError("Invalid script")

# Execute without type checking (already validated)
cy_executor = Cy(check_types=False, tools=tools)
result = cy_executor.run(script, input_data)
```

## Complete Example

```python
from cy_language import Cy
from typing import Dict, List

# Define custom tools with type hints
def fetch_ip_reputation(ip_address: str) -> dict:
    """Fetch IP reputation from VirusTotal."""
    # API call implementation...
    return {
        "ip": ip_address,
        "malicious_score": 8,
        "reputation": "suspicious"
    }

def calculate_risk_score(malicious_score: int, open_ports: int) -> int:
    """Calculate risk score."""
    return malicious_score * 10 + open_ports

def format_report(ip: str, risk_score: int, reputation: str) -> dict:
    """Format security report."""
    return {
        "ip": ip,
        "risk_score": risk_score,
        "reputation": reputation,
        "severity": "HIGH" if risk_score > 70 else "MEDIUM" if risk_score > 30 else "LOW"
    }

# Register tools
tools = {
    "app::virustotal::ip_reputation": fetch_ip_reputation,
    "app::security::calculate_risk": calculate_risk_score,
    "app::security::format_report": format_report
}

# Create Cy compiler instance
# Note: Input schema is auto-derived from input_data when check_types=True
cy = Cy(
    check_types=True,
    tools=tools
)

# Cy workflow script
script = """
# Get input
ip = input.ip_address
ports = input.open_ports

# Fetch IP reputation
vt_data = app::virustotal::ip_reputation(ip_address=ip)

# Calculate risk
risk = app::security::calculate_risk(
    malicious_score=vt_data.malicious_score,
    open_ports=ports
)

# Format final report
report = app::security::format_report(
    ip=ip,
    risk_score=risk,
    reputation=vt_data.reputation
)

return report
"""

# Execute workflow
input_data = {
    "ip_address": "8.8.8.8",
    "open_ports": 22
}

result = cy.run(script, input_data)
print("\nExecution result:")
print(result)
# {
#   "ip": "8.8.8.8",
#   "risk_score": 102,
#   "reputation": "suspicious",
#   "severity": "HIGH"
# }
```

## Quick Reference

### Creating Compiler Instance

```python
# Basic
cy = Cy()

# With type checking (schema auto-derived from input_data)
cy = Cy(check_types=True)

# With tools
cy = Cy(tools={...})

# With log capture
logs = []
cy = Cy(captured_logs=logs)

# Full configuration
cy = Cy(
    check_types=True,
    tools={...},
    captured_logs=[],
    enable_parallel=True
)
```

### Running Scripts

```python
# Without input
result = cy.run(script)

# With input (schema auto-derived when check_types=True)
result = cy.run(script, input_data)
```

### Static Analysis (Standalone Function)

```python
from cy_language import analyze_types

# Static analysis without execution
output_schema = analyze_types(
    code=script,
    input_schema={"type": "object", "properties": {...}}
)
```

### Tool Registration Format

```python
tools = {
    "app::category::function_name": python_function
}
```

### Input Schema Format (for analyze_types() only)

**Note:** Input schemas are NOT passed to `Cy()` - they're auto-derived from `input_data`. Only use explicit schemas with the standalone `analyze_types()` function.

```python
# For standalone analyze_types() function only
input_schema = {
    "type": "object",
    "properties": {
        "field_name": {"type": "string"},
        "count": {"type": "number"},
        "active": {"type": "boolean"},
        "nested": {
            "type": "object",
            "properties": {
                "sub_field": {"type": "string"}
            }
        }
    }
}
```
