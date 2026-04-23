# Cy Language Control Flow

Complete reference for if/elif/else, for-in loops, while loops, conditional expressions, and error handling.

## If/Elif/Else Statements

Standard conditional execution with C-style braces:

```cy
# Basic if/else
score = 85
grade = "F"
if (score >= 90) {
    grade = "A"
} elif (score >= 80) {
    grade = "B"
} else {
    grade = "C"
}
```

**Syntax notes:**
- Condition must be in parentheses: `if (condition)`
- Blocks use curly braces `{}`
- `elif` (not `else if`)

## Conditional Expressions

Returns a value based on condition - perfect for assignments:

```cy
# Ternary-like expression
score = 85
grade = if (score >= 90) { "A" } elif (score >= 80) { "B" } else { "C" }

# Use in arithmetic expressions
x = 5
result = (if (x > 3) { 10 } else { 20 }) + 5  # result = 15

# Nested conditional expressions
age = 25
category = if (age < 13) { "child" } elif (age < 18) { "teen" } else { if (age < 65) { "adult" } else { "senior" } }
```

**Type behavior:**
- If branches return different types, creates a union type:
```cy
flag = True
value = if (flag) { 42 } else { "text" }  # Type: number | string
```

## For-In Loops (Auto-parallelizable)

Iterate over lists and dictionaries with automatic parallelization support:

```cy
# Iterate over lists
items = [1, 2, 3, 4, 5]
results = []
for (item in items) {
    processed = item * 2
    results = results + [processed]  # Use + for list concatenation
}
# results = [2, 4, 6, 8, 10]

# Iterate over dictionaries (iterates over KEYS like Python/JavaScript)
scores = {"Alice": 95, "Bob": 87, "Carol": 92}
report = []
for (name in scores) {
    score = scores[name]  # Access value using key
    report = report + ["${name}: ${score}"]
}
# report = ["Alice: 95", "Bob: 87", "Carol: 92"]
```

**Important:** When iterating over dicts, `for (key in my_dict)` yields the **keys**, not values. Access values with `my_dict[key]`.

### Nested Loops

```cy
# Nested for-in loops
matrix_result = []
for (row in [[1, 2], [3, 4]]) {
    for (col in row) {
        matrix_result = matrix_result + [col * 10]
    }
}
# matrix_result = [10, 20, 30, 40]
```

### Conditionals in Loops

```cy
# Filter with for-in and if
numbers = [1, 2, 3, 4, 5, 6]
evens = []
for (num in numbers) {
    if (num % 2 == 0) {
        evens = evens + [num]
    }
}
# evens = [2, 4, 6]
```

## List Comprehensions

Compact syntax for transforming and filtering lists — replaces the for-loop + accumulator pattern:

```cy
# Basic: extract a field from each element
ids = [u.id for(u in users)]

# With filter: only include matching elements
admins = [u.name for(u in users) if(u.role == "admin")]
```

**Syntax:**
- `[expr for(var in iterable)]` — transform each element
- `[expr for(var in iterable) if(condition)]` — transform + filter

### Field Extraction

```cy
users = [
    {"id": "U001", "name": "Alice", "role": "admin"},
    {"id": "U002", "name": "Bob", "role": "user"}
]

names = [u.name for(u in users)]          # ["Alice", "Bob"]
ids = [u.id for(u in users)]              # ["U001", "U002"]
```

### Transform Elements

```cy
nums = [1, 2, 3, 4, 5]
doubled = [n * 2 for(n in nums)]          # [2, 4, 6, 8, 10]
evens = [n for(n in nums) if(n % 2 == 0)] # [2, 4]
```

### With Tool Calls and String Interpolation

```cy
words = ["hello", "world"]
upper = [str::uppercase(w) for(w in words)]   # ["HELLO", "WORLD"]

greetings = ["Hello ${u.name}!" for(u in users)]
```

### Nested Field Access

```cy
records = [
    {"profile": {"email": "a@x.com"}},
    {"profile": {"email": "b@x.com"}}
]
emails = [r.profile.email for(r in records)]  # ["a@x.com", "b@x.com"]
```

### As Expression (in function args, return, etc.)

```cy
# Directly in len()
admin_count = len([u.name for(u in users) if(u.role == "admin")])

# In return
return [item.id for(item in results)]
```

### Dict Iteration (iterates over keys)

```cy
d = {"a": 1, "b": 2, "c": 3}
all_keys = [k for(k in d)]  # ["a", "b", "c"]
```

### When to Use Comprehensions vs For-In Loops

```cy
# Comprehensions — for simple extract/transform/filter
ids = [u.id for(u in users)]
evens = [n for(n in numbers) if(n % 2 == 0)]

# For-in loops — for complex bodies, side effects, or multi-step logic
for (item in items) {
    log("Processing: ${item.name}")
    result = expensive_operation(item)
    results = results + [result]
}
```

### Parallel Execution

For-in loops can execute in parallel automatically:

```cy
# These API calls run in parallel
urls = ["api.com/user1", "api.com/user2", "api.com/user3"]
responses = []
for (url in urls) {
    response = fetch(url)  # Calls happen concurrently!
    responses = responses + [response]
}
```

**Auto-parallelization conditions:**
- Loop body has no dependencies between iterations
- Each iteration is self-contained
- Cy's execution engine detects and optimizes automatically

## While Loops

Traditional while loop for conditional iteration:

```cy
# Basic while loop
counter = 0
total = 0
while (counter < 5) {
    total = total + counter
    counter = counter + 1
}
# total = 10 (0+1+2+3+4)
```

**Warning:** While loops don't auto-parallelize. Use for-in when possible.

## Loop Control: Break and Continue

Use `break` to exit a loop early and `continue` to skip to the next iteration.

### Break — Early Loop Exit

<!-- cy-test: compile-only -->
```cy
for (item in items) {
    if (condition) {
        break
    }
}
```

### Continue — Skip Iteration

<!-- cy-test: compile-only -->
```cy
for (item in items) {
    if (skip_condition) {
        continue
    }
    process(item)
}
```

### Find First Match with Break

```cy
# Find first matching item and stop
items = ["apple", "banana", "cherry", "date"]
target = "cherry"
result = null

for (item in items) {
    if (item == target) {
        result = item
        break
    }
}

return {"found": result != null, "result": result}
```

### Filter with Continue

```cy
# Collect only valid entries, skip nulls
entries = [1, null, 3, null, 5]
valid = []
for (e in entries) {
    if (e == null) {
        continue
    }
    valid = valid + [e]
}
return valid
```

### Nested Loops

`break` and `continue` apply to the **innermost** enclosing loop only:

```cy
results = []
for (i in [1, 2, 3]) {
    for (j in [10, 20, 30]) {
        if (j == 20) {
            break
        }
        results = results + [i * 100 + j]
    }
}
return results
```

### Compile-Time Validation

`break` and `continue` can only appear inside a loop body. Using them outside a loop is a compile-time error.

## Early Return

Exit function/script early with `return`:

```cy
# Validation with early return
value = input["amount"]
if (value < 0) {
    return "Error: negative value"
}

# Continue with normal processing
output = "Processing amount: ${value}"
return output
```

**Multiple returns in branches:**
```cy
score = 85
if (score >= 90) {
    return "Excellent"
} elif (score >= 70) {
    return "Good"
} else {
    return "Needs improvement"
}
```

## Error Handling (Try/Catch)

Comprehensive error handling with try/catch/finally blocks:

### Basic Try/Catch

```cy
# Handle division by zero
result = "success"
try {
    value = 10 / 0
} catch (e) {
    result = "Error: ${e}"
}
# result = "Error: Line 3, Col 17: Division by zero"
```

### Multiple Error Handling

```cy
# Collect multiple errors
errors = []

try {
    x = undefined_variable
} catch (e) {
    errors = errors + ["${e}"]
}

try {
    result = some_tool()
} catch (e) {
    errors = errors + ["${e}"]
}

return {"errors": errors}
```

### Try/Catch/Finally

```cy
# Cleanup with finally block
cleanup_done = False
result = "default"

try {
    data = risky_operation()
    result = data
} catch (e) {
    result = "Failed: ${e}"
} finally {
    cleanup_done = True  # Always executes, even if return in try/catch
}
```

### Nested Error Handling (Fallbacks)

```cy
# Try primary method, fallback to secondary
result = ""
try {
    result = primary_api_call()
} catch (e1) {
    try {
        result = fallback_api_call()
    } catch (e2) {
        result = "All methods failed: ${e2}"
    }
}
```

## Common Patterns

### Data Validation

```cy
# Validate input before processing
data = input["data"]

if (len(data) == 0) {
    return {"error": "Empty data"}
}

# Process valid data
results = []
for (item in data) {
    results = results + [process(item)]
}
return {"results": results}
```

### Accumulator Pattern

```cy
# Collect results from iterations
items = ["apple", "banana", "cherry"]
messages = []

for (item in items) {
    message = "Processing ${item}"
    log(message)  # Log doesn't affect output
    messages = messages + [message]
}

return {"processed": len(items), "messages": messages}
```

### Conditional Processing Pipeline

```cy
# Multi-step conditional pipeline
score = input["score"]
status = "unknown"

if (score >= 90) {
    status = "excellent"
    bonus = 100
} elif (score >= 70) {
    status = "good"
    bonus = 50
} else {
    status = "needs_improvement"
    bonus = 0
}

return {
    "status": status,
    "bonus": bonus,
    "message": "Performance is ${status}"
}
```

### Error Recovery Workflow

```cy
# Try with multiple fallback strategies
results = []

for (item in items) {
    try {
        # Try primary processing
        result = expensive_operation(item)
        results = results + [result]
    } catch (e) {
        # Fallback to simpler processing
        try {
            simple_result = simple_operation(item)
            results = results + [simple_result]
        } catch (e2) {
            # Log error but continue
            log("Failed to process ${item}: ${e2}")
            results = results + [{"error": "${e2}"}]
        }
    }
}

return results
```

## Control Flow Tips

### ✅ Do This
- Use list comprehensions for extracting/transforming/filtering lists
- Use for-in for parallel-friendly iterations with complex bodies
- Use conditional expressions for simple value selection
- Use early returns for validation
- Wrap risky operations in try/catch
- Use finally for cleanup that must always run

### ❌ Avoid This
- Don't use `break`/`continue` outside loops (compile error)
- Don't use while when for-in would work (loses parallelization)
- Note: `break`/`continue` in for-in disables auto-parallelization
- Don't nest too many levels (consider breaking into functions)
- Don't swallow errors without logging them
- Don't use for-in if iterations depend on each other

## Quick Reference

| Feature | Syntax | Parallel-safe? | Notes |
|---------|--------|----------------|-------|
| If/elif/else | `if (cond) { } elif { } else { }` | ✅ Yes | |
| Conditional expr | `if (cond) { val1 } else { val2 }` | ✅ Yes | |
| For-in loop | `for (item in items) { }` | ✅ **Auto-parallel** | |
| List comprehension | `[expr for(x in items)]` | ✅ Yes | |
| List comp + filter | `[expr for(x in items) if(cond)]` | ✅ Yes | |
| While loop | `while (cond) { }` | ❌ Sequential only | |
| Break | `break` | ✅ Yes | Exits innermost loop |
| Continue | `continue` | ✅ Yes | Skips to next iteration |
| Early return | `return value` | ✅ Yes | |
| Try/catch | `try { } catch (e) { }` | ✅ Yes | |
| Try/finally | `try { } finally { }` | ✅ Yes | |
