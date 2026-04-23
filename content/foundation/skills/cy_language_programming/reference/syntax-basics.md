# Cy Language Syntax Basics

Quick reference for Cy's core syntax elements - variables, strings, data structures, and operators.

## Language Design Philosophy

Cy combines familiar syntax from multiple languages:

- **Python-style**: Comments (`#`), variable assignments, data structures (lists `[]`, dictionaries `{}`), function calls `func(args)`, and logical operators (`and`, `or`, `not`)
- **Bash-style**: String interpolation with `${expr}` syntax
- **C-style**: Code blocks with curly braces `{}`

This combination creates a familiar yet unique syntax optimized for scripting and data processing.

## Variables and Assignment

Variables work like Python - clean and simple:

```cy
# Variable assignments (Python-style)
name = "Alice"
age = 30
is_active = True    # Use True/False (capitalized)

# Lists and dictionaries (Python-style)
fruits = ["apple", "banana", "cherry"]
user = {
    "name": "Alice",
    "age": 30,
    "hobbies": ["reading", "coding"]
}
```

### Compound Assignment Operators

```cy
# Compound operators (shorthand for x = x op y)
count = 10
count += 5    # count = count + 5 → 15
count -= 3    # count = count - 3 → 12
count *= 2    # count = count * 2 → 24
count /= 4    # count = count / 4 → 6
count %= 4    # count = count % 4 → 2

# Works with strings too
text = "Hello"
text += " World"  # text = "Hello World"

# Works with lists
items = [1, 2]
items += [3, 4]   # items = [1, 2, 3, 4]
```

**Important Notes:**
- `$` is **only** used inside string interpolation: `"Hello ${name}"`
- Reserved literals: `True`, `False` (capitalized!), `null` (evaluates to Python's `None`)
- **All programs must end with `return` statement** to produce output

```cy
name = "Alice"
output = "Hello ${name}!"
return output  # Required!
```

## Strings

Cy supports two string syntaxes:

### Single-line Strings
```cy
name = "Alice"
message = "Hello, world!"
```

### Multiline Strings (Triple Quotes)

**⚠️ IMPORTANT: Always use `"""` for multiline strings!**

```cy
# ✅ CORRECT - Triple quotes for multiline
prompt = """This is a multiline string.
It can span multiple lines.
Very useful for LLM prompts."""

# ❌ WRONG - Don't use \n or concatenation
prompt = "Line 1\nLine 2\nLine 3"  # Hard to read
prompt = "Line 1\n" + "Line 2\n"   # Verbose
```

**Why use `"""`?**
- More readable, especially for long prompts
- Preserves formatting and whitespace
- Works seamlessly with `${var}` interpolation
- Essential for `llm_run()` prompts

## String Interpolation

Use `${...}` to insert variable values into strings (Bash-style):

```cy
# Basic interpolation
name = "Alice"
age = 30
greeting = "Hello ${name}!"
message = "User ${name} is ${age} years old"

# Object property access in interpolation
user = {"name": "Alice", "email": "alice@example.com"}
info = "Contact: ${user.name} at ${user.email}"

# ✅ BEST PRACTICE: Multiline with interpolation (for LLM prompts)
prompt = """Analyze this alert:
Title: ${alert.title}
Severity: ${alert.severity}
Source IP: ${alert.source_ip}

Provide:
1. A risk assessment
2. Recommended actions"""

result = llm_run(prompt=prompt)
```

### Advanced Interpolation

Complex expressions work inside `${}`:

```cy
# Function calls and arithmetic
items = ["apple", "banana", "cherry"]
multiplier = 2.5
result = "Processing item ${(len(items) * multiplier) / 2 + 11.1}"

# Boolean logic
age = 25
score = 85
status = "User is ${age >= 18 and score > 80}"

# Nested data access
data = {"users": [{"name": "Alice"}]}
output = "User: ${data['users'][0]['name']}"
```

**Interpolation is a type escape hatch**: It accepts **Any** type and converts everything to string.

### String Building Best Practices

**For building long strings (especially LLM prompts), prefer multiline interpolation over concatenation:**

```cy
# ✅ PREFERRED: Multiline interpolation for readability
prompt = """Alert Context: ${alert_context}

Analyze this IP reputation for ${source_ip}:
- Detections: ${detections}/80
- Risk level: ${risk_level}

Provide 2-sentence summary."""

analysis = llm_run(prompt=prompt)
```

```cy
# ❌ AVOID: String concatenation gets verbose and hard to read
prompt = "Alert Context: " + alert_context + "

Analyze this IP reputation for " + source_ip + ":
- Detections: " + str(detections) + "/80
- Risk level: " + risk_level + "

Provide 2-sentence summary."

analysis = llm_run(prompt=prompt)
```

**Why prefer interpolation:**
- **More readable:** Variables blend naturally into the text
- **Less verbose:** No `+` operators and quote management
- **Cleaner for long prompts:** LLM prompts with many variables stay readable
- **Natural formatting:** Multiline strings preserve whitespace and structure

**When concatenation is okay:**
- Very short strings where interpolation adds noise
- Dynamic string building in loops

## Data Structure Access

**⚠️ IMPORTANT: Cy is NOT Object-Oriented**

Cy does not have methods or properties on primitive types (strings, numbers, lists). The dot operator (`.`) is **only for dictionary field access**, not OOP method calls.

**Common LLM mistakes:**
<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - No methods on strings
text = "hello"
parts = text.split(",")    # ERROR: .split() is not a method
size = text.length          # ERROR: .length property doesn't exist

# ✅ CORRECT - Use native functions
parts = split(text, ",")    # split() is a function, not method
size = len(text)            # len() is a function, not property

# ❌ WRONG - No methods on lists
items = [1, 2, 3]
items.push(4)               # ERROR: .push() doesn't exist
doubled = items.map(f)      # ERROR: .map() doesn't exist

# ✅ CORRECT - Use operators and list comprehensions
items = items + [4]                       # Concatenation
doubled = [item * 2 for(item in items)]   # List comprehension
```

**When dot notation DOES work:**
```cy
# ✅ Dictionary field access (the ONLY valid use of dot)
user = {"name": "Alice", "email": "alice@example.com"}
name = user.name            # OK: accessing dict field
user.age = 30               # OK: setting dict field
```

Two syntax options for accessing data:

```cy
user = {
    "name": "Alice",
    "contact": {"email": "alice@example.com"},
    "scores": [85, 92, 78]
}

# Outside interpolation - both work for objects
name = user.name              # Dot notation
name = user["name"]           # Bracket notation
first_score = user["scores"][0]  # Brackets for lists

# Inside interpolation ${} - use dot notation for objects
output = "User: ${user.name}, Email: ${user.contact.email}"
output2 = "First score: ${user.scores[0]}"
```

### Indexed Assignment

Modify dictionaries and lists in place:

```cy
# Dictionary assignment
data = {"name": "Alice"}
data["age"] = 30
data["active"] = True

# List assignment
items = ["a", "b", "c"]
items[0] = "x"
items[2] = "z"

# Variable keys/indices
scores = {}
player = "alice"
scores[player] = 95
```

### Field Assignment

Use dot notation to assign dictionary fields - cleaner syntax than bracket notation:

```cy
# ✅ Field assignment
alert = {}
alert.severity = "high"              # Equivalent to: alert["severity"] = "high"
alert.source_ip = "192.168.1.100"

# Auto-creates intermediate dictionaries (JavaScript-style)
alert.enrichment.geo.country = "US"  # Creates nested structure automatically!
# Equivalent to:
# alert["enrichment"] = {}
# alert["enrichment"]["geo"] = {}
# alert["enrichment"]["geo"]["country"] = "US"

# Works with compound operators
data.count += 1              # data["count"] = data["count"] + 1
alert.tags += ["suspicious"] # Append to list

# Auto-create behavior
config = {}
config.x.y.z = 5            # Creates: {"x": {"y": {"z": 5}}}

# Null values automatically become empty dicts
settings = {"theme": null}
settings.theme.colors.primary = "blue"  # theme becomes {}, then adds nested fields

# Preserves existing fields when auto-creating
user = {"profile": {"name": "Alice"}}
user.profile.email = "alice@example.com"  # profile.name still exists

# Compound assignment on nested fields
result.scores.total += 10
data.metrics.count *= 2
```

**Important Notes:**
- Only works on dictionaries (not primitives like numbers, strings, lists)
- Auto-creates intermediate dicts if missing or null
- Mixed notation NOT supported: `obj.field["key"].value` → **Syntax error**
- Use consistent notation: all dots OR all brackets

**Why use field assignment?**
- **Cleaner**: `alert.severity = "high"` vs `alert["severity"] = "high"`
- **Less typing**: No quotes and brackets
- **Auto-create**: No need to manually create intermediate dicts
- **Consistent**: Matches field access syntax (`alert.severity`)

## Data Structures

### Lists

```cy
# List literals
fruits = ["apple", "banana", "cherry"]
numbers = [1, 2, 3, 4, 5]
mixed = [1, "two", True, {"key": "value"}]

# Empty list
items = []

# List concatenation (use + operator)
combined = [1, 2] + [3, 4]  # [1, 2, 3, 4]

# Append to list
results = []
results = results + [new_item]

# List comprehensions - extract/transform/filter
names = [u.name for(u in users)]
evens = [n for(n in nums) if(n % 2 == 0)]

# Access elements
first = fruits[0]
last = fruits[2]

# Negative indexing (Python-style)
last = fruits[-1]       # Last element
second_last = fruits[-2]  # Second to last
```

### Dictionaries (Objects)

**Important:** Dictionary keys **must be strings** (JSON-compatible). Integer or other types as keys are not supported.

```cy
# Dictionary literals
user = {
    "name": "Alice",
    "age": 30,
    "contact": {
        "email": "alice@example.com",
        "phone": "555-1234"
    }
}

# Empty dictionary
config = {}

# Nested access
email = user["contact"]["email"]
email = user.contact.email  # Alternative (outside interpolation)

# ✅ Keys must be strings
data = {"field1": 10, "field2": 20}

# ❌ Non-string keys not allowed
# data = {1: "value"}        # Syntax error
# data = {True: "value"}     # Syntax error
```

## Mathematical and Logical Operations

```cy
# Math operations
sum = 10 + 5
product = 4 * 3
difference = 20 - 8
ratio = amount / balance
remainder = 15 % 4

# Comparison operators
is_large = amount > 1000
is_equal = x == y
not_equal = x != y
greater_eq = x >= 5
less_eq = x <= 10

# Logical operators (MUST use English words - symbols cause syntax errors!)
needs_review = is_large and ratio > 0.3  # ✅ Correct
is_valid = not is_error                   # ✅ Correct
either = option1 or option2               # ✅ Correct
# result = a && b   # ❌ Syntax error! Use 'and'
# result = a || b   # ❌ Syntax error! Use 'or'
# result = !flag    # ❌ Syntax error! Use 'not'

# Chained comparisons (Python-style)
is_middle = 1 < x < 10  # Equivalent to: x > 1 and x < 10
in_range = min_val <= value <= max_val

# Operator precedence (same as Python)
result = 10 + 5 * 2  # 20 (multiplication first)
result = (10 + 5) * 2  # 30 (parentheses override)
```

## Comments

```cy
# Single line comment (Python-style)

# Multiple single-line comments
# can be used for
# multi-line documentation

x = 10  # Inline comment after code
```

## Common Syntax Mistakes

### ❌ Using Python's `None` literal
```cy
# ❌ WRONG - None is not a Cy keyword
value = None

# ✅ CORRECT - use null instead
value = null      # Cy's null literal (evaluates to Python's None)
value = ""        # Empty string
value = False     # Boolean
value = []        # Empty list
value = {}        # Empty dict
```

### ❌ Forgetting `return` statement
```cy
# ❌ WRONG
name = "Alice"
output = "Hello ${name}!"
# Missing return - program has no output!

# ✅ CORRECT
name = "Alice"
output = "Hello ${name}!"
return output
```

### ❌ Using `$` outside interpolation
<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - $ is only for interpolation
$name = "Alice"      # Not allowed!
$output = $name      # Not allowed!

# ✅ CORRECT - $ only inside strings
name = "Alice"
output = "Hello ${name}"  # This is where $ belongs
```

### ❌ Double quotes in dict access inside interpolation
<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - double quotes conflict with string delimiters
output = "User: ${user["name"]}"  # Parsing error!

# ✅ CORRECT - use single quotes for dict keys
output = "User: ${user['name']}"

# ✅ PREFERRED - use dot notation (cleaner syntax)
output = "User: ${user.name}"
```

### ❌ Using non-string dictionary keys
<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - keys must be strings
data = {1: "value"}           # Syntax error
data = {True: "value"}        # Syntax error
scores = {user_id: score}     # Syntax error (variable as key)

# ✅ CORRECT - use string keys
data = {"1": "value"}
data = {"true": "value"}
scores = {}
scores["user_123"] = 95
```

### ❌ Using lowercase booleans
```cy
# ❌ WRONG - causes runtime error
is_active = true       # Runtime error!
is_valid = false       # Runtime error!

# ✅ CORRECT - must be capitalized
is_active = True
is_valid = False
```

### ❌ Using semicolons (JavaScript/C habit)
<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - semicolons not needed
x = 5;
y = 10;

# ✅ CORRECT - no semicolons
x = 5
y = 10
```

### ❌ Assignment in conditions

<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - = is assignment, not comparison
if (x = 10) {
    result = "changed"
}
```

```cy
# ✅ CORRECT - use == for comparison
if (x == 10) {
    result = "equal"
}
```

### ❌ Using else if instead of elif
<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - "else if" is two words
} else if (x > 5) {
    result = "medium"
}

# ✅ CORRECT - use elif
} elif (x > 5) {
    result = "medium"
}
```

### ❌ Missing function call parentheses
```cy
# ❌ WRONG - referencing function without calling it
items = [1, 2, 3]
length = len

# ✅ CORRECT - add () to call function
length = len(items)
```

### Numeric iteration with `range()`
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
evens = range(0, 10, 2)     # [0, 2, 4, 6, 8]

# Reverse
countdown = range(5, 0, -1) # [5, 4, 3, 2, 1]
```

### Containment `in` operator
Cy supports `in` for both iteration (`for (x in items)`) and containment tests:

```cy
# List membership
found = 2 in [1, 2, 3]          # True

# String substring check
has_match = "world" in "hello world"  # True

# Dict key lookup
exists = "name" in {"name": "Alice"}  # True
```

## Input Variable

Access input data passed to the script:

```cy
# Access input fields
ip_address = input["ip"]
user_id = input.user_id  # Dot notation alternative

# With type checking (check_types=True)
ip = input["ip_address"]  # Type auto-inferred from input_data
```

## Quick Syntax Checklist

✅ **DO:**
- Use `#` for comments
- Variables: `name = "value"` ($ only in interpolation!)
- Strings: `"text"` for single line
- **Multiline: `"""text"""` (ALWAYS use for LLM prompts!)**
- Interpolation: `"Hello ${name}"` or `"""Hello ${name}"""`
- Lists: `[1, 2, 3]`
- Dicts: `{"key": "value"}` (keys must be strings)
- Booleans: `True`, `False` (capitalized!)
- Null: `null` (evaluates to Python's `None`)
- End with: `return result`
- Logical ops: `and`, `or`, `not`
- Field assignment: `obj.field = value`
- Numeric iteration: `range(10)`, `range(0, 10)`, or `range(0, 10, 2)`
- List comprehensions: `[x.name for(x in items) if(x.active)]`
- Use `elif` (not `else if`)

❌ **DON'T:**
- Lowercase booleans true/false → Runtime error!
- Symbol operators && or || or ! → Syntax error!
- Dollar sign outside interpolation → Not allowed
- `else if` → Use `elif`
- Mixed notation in field assignment → Syntax error (`obj.field["key"]` not supported)
- String concatenation for multiline → Use `"""` instead
