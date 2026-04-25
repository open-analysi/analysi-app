# Type-Safe Workflow Template
# Use with: cy = Cy(check_types=True, tools={...})

# Python setup (run before executing this script):
"""
from cy_language import Cy

# Register tools with type hints
def my_tool(arg1: str, arg2: int) -> dict:
    return {"result": f"{arg1}-{arg2}"}

tools = {
    "app::custom::my_tool": my_tool
}

# Create type-checked compiler
cy = Cy(
    check_types=True,
    tools=tools
)

# Input data with typed fields (schema auto-derived when check_types=True)
input_data = {
    "field1": "hello",    # Inferred as string
    "field2": 42,         # Inferred as number
    "field3": True        # Inferred as boolean
}

# Run script - schema is automatically derived from input_data
result = cy.run(script, input_data)
"""

# Cy Script (type-checked at compile-time):

# Access typed input fields
field1 = input.field1  # Type: string
field2 = input.field2  # Type: number
field3 = input.field3  # Type: boolean

log("Processing typed workflow...")

# Type-checked tool call
tool_result = app::custom::my_tool(
    arg1=field1,     # Type: string
    arg2=field2      # Type: number
)

# Type-safe operations
if (field3) {
    status = "enabled"
} else {
    status = "disabled"
}

# Type-checked arithmetic
calculated = field2 * 2

# Build typed output
result = {
    "field1": field1,
    "field2": field2,
    "calculated": calculated,
    "status": status,
    "tool_result": tool_result
}

return result

# Type checking benefits:
# - Input fields validated against schema
# - Tool arguments validated against Python type hints
# - Operations validated (string + string, number + number)
# - Errors caught BEFORE execution
# - Better IDE support and documentation
