# Basic Cy Script Template
# Copy and modify this template for your workflow

# Access input data
data = input.field_name

# Log progress (doesn't affect output)
log("Starting processing...")

# Process data
result = process_data(data)

# Build output structure
output = {
    "status": "success",
    "result": result,
    "message": "Processing complete"
}

# Return output (required!)
return output

# Tips:
# - All programs must end with 'return' statement
# - Use ${variable} for string interpolation
# - Use log() for debugging without affecting output
# - Lists: [1, 2, 3], Dicts: {"key": "value"}
# - Conditionals: if (condition) { } else { }
# - Loops: for (item in items) { }
