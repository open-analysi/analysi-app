# Cy Language Functions and Tools

Complete reference for native functions, tool calls, and the namespace system.

## Namespace System (FQN)

Cy uses Fully Qualified Names (FQNs) to organize tools across different sources:

```cy
# Native functions - can use short names or FQNs
count = len([1, 2, 3])                       # Short name (resolves to native::tools::len)
count = native::tools::len([1, 2, 3])        # Explicit FQN

# App namespace tools (integration tools from your app)
result = app::test::test1("data")
analysis = app::virustotal::ip_reputation(ip="8.8.8.8")

# Archetype namespace tools
processed = arc::example::analyze("data")

# MCP calls (requires async setup) - always use FQN
math_result = mcp::demo::add(a=10, b=15)
ip_check = mcp::virustotal::virustotal_ip_reputation(ip="8.8.8.8")
```

### Ambiguity Handling

The compiler detects name conflicts at compile time:

```cy
# If both app::tools::process and native::tools::process exist:

# ✅ Explicit FQN - works
app::tools::process(data)
native::tools::process(data)

# ❌ Ambiguous - compile error with helpful message
process(data)  # ERROR: Ambiguous tool 'process'
```

## Native Functions (45 Built-ins)

These functions are **always available** - no imports or registration needed.

### Data Functions

#### `len(arg)` - Get Length

Returns the length of a string, list, or dictionary:

```cy
# Lists
my_list = ["apple", "banana", "cherry"]
count = len(my_list)              # Returns: 3

# Strings
text = "Hello"
chars = len(text)                 # Returns: 5

# Dictionaries (counts keys)
data = {"name": "Alice", "age": 30}
fields = len(data)                # Returns: 2
```

#### `sum(items)` - Sum Numbers

Sums all numbers in a list:

```cy
numbers = [1, 2, 3, 4, 5]
total = sum(numbers)              # Returns: 15

# Calculate average
scores = [85, 92, 78]
average = sum(scores) / len(scores)  # 85.0
```

#### `str(value)` - Convert to String

Converts any value to a string:

```cy
num = 42
text = str(num)                   # Returns: "42"

# Concatenation without interpolation
result = "The answer is " + str(num)  # "The answer is 42"

# Works with any type
data = [1, 2, 3]
text = str(data)                  # "[1, 2, 3]"
```

#### `int(value)` - Convert to Integer

Converts a value to an integer:

```cy
# Convert string to integer
text = "42"
num = int(text)                   # Returns: 42

# Convert float to integer (truncates)
decimal = 3.14
whole = int(decimal)              # Returns: 3

# Use in calculations
user_input = "100"
result = int(user_input) + 50     # 150

# Error handling
try {
    value = int("not_a_number")   # Raises ValueError
} catch (e) {
    log("Conversion error: ${e}")
}
```

### JSON Functions

#### `from_json(json_string)` - Parse JSON

Parses JSON string to structured data:

```cy
json_text = '{"name": "Alice", "age": 30}'
user = from_json(json_text)
name = user.name                  # "Alice"
age = user.age                    # 30

# Parse JSON arrays
json_array = '["apple", "banana", "cherry"]'
fruits = from_json(json_array)
count = len(fruits)               # Returns: 3
```

#### `to_json(data, [indent])` - Serialize to JSON

Converts data structure to JSON string:

```cy
user = {"name": "Bob", "age": 25}
json_output = to_json(user)       # '{"name": "Bob", "age": 25}'

# Pretty-print with indentation
pretty = to_json(user, 2)         # Formatted with 2-space indent
output = "User data:\n${pretty}"

# Complex data
data = {
    "users": [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
    ]
}
json_str = to_json(data, 2)       # Nested pretty-print
```

### String Functions

#### `uppercase(text)` - Convert to Uppercase

```cy
name = "alice"
upper_name = uppercase(name)      # Returns: "ALICE"

# Use in interpolation
output = "Hello ${uppercase(name)}"  # Hello ALICE
```

#### `lowercase(text)` - Convert to Lowercase

```cy
name = "BOB"
lower_name = lowercase(name)      # Returns: "bob"

# Use in interpolation
output = "username: ${lowercase(name)}"  # username: bob
```

#### `join(items, [separator])` - Join List with Separator

Joins list items with separator (default: ", "):

```cy
fruits = ["apple", "banana", "cherry"]
csv = join(fruits, ", ")          # "apple, banana, cherry"

# Custom separator
path = join(["home", "user", "docs"], "/")  # "home/user/docs"

# Default separator (comma-space)
list = ["a", "b", "c"]
result = join(list)               # "a, b, c"
```

### Logging Function

#### `log(message)` - Log Without Affecting Output

Logs messages to stderr without interfering with program output:

```cy
# Basic logging
log("Processing started")
items = ["a", "b", "c"]
log("Found ${len(items)} items")

# Standalone logging in loops
for (item in items) {
    log("Processing: ${item}")     # Logs each item
}

# Logging in error handling
try {
    result = risky_operation()
} catch (e) {
    log("Error occurred: ${e}")    # Logged, doesn't affect output
}

return "Success"  # This is the output
```

**Key feature:** `log()` works as a standalone statement - you don't need to assign its result.

### Type Conversion Functions

#### `num(value)` - Convert to Number (Float)

Converts values to floating-point numbers:

```cy
# String to number
price = num("42.50")              # Returns: 42.5
age = num("30")                   # Returns: 30.0

# Integer to float
count = num(100)                  # Returns: 100.0

# Boolean to number
active = num(True)                # Returns: 1.0
inactive = num(False)             # Returns: 0.0

# With whitespace
value = num("  3.14  ")           # Returns: 3.14
```

#### `bool(value)` - Convert to Boolean

Converts values to boolean with string representation support:

```cy
# String representations
flag1 = bool("true")              # Returns: True
flag2 = bool("FALSE")             # Returns: False
flag3 = bool("1")                 # Returns: True
flag4 = bool("0")                 # Returns: False

# Numeric truthiness
flag5 = bool(1)                   # Returns: True
flag6 = bool(0)                   # Returns: False

# Collection truthiness
flag7 = bool([1, 2])              # Returns: True (non-empty)
flag8 = bool([])                  # Returns: False (empty)
```

### Time Functions

#### `now([timezone])` - Get Current Timestamp

Returns current timestamp in ISO 8601 format:

```cy
# UTC (default)
timestamp = now()                 # "2025-10-31T14:30:00Z"

# Specific timezone
pst_time = now("US/Pacific")      # "2025-10-31T06:30:00-08:00"
london_time = now("Europe/London") # "2025-10-31T14:30:00+00:00"

# Use in data
event = {
    "action": "login",
    "timestamp": now(),
    "user": "alice"
}
```

### Iteration Functions

#### `range(end)` / `range(start, end, [step])` - Generate Number List

Creates a list of numbers. Single-arg form starts from 0; two/three-arg form specifies start (inclusive) and end (exclusive):

```cy
# Single-arg: range(end) — starts from 0
numbers = range(5)                # [0, 1, 2, 3, 4]

# Two-arg: range(start, end)
numbers = range(2, 7)             # [2, 3, 4, 5, 6]

# With step
evens = range(0, 10, 2)           # [0, 2, 4, 6, 8]
odds = range(1, 10, 2)            # [1, 3, 5, 7, 9]

# Reverse range
countdown = range(5, 0, -1)       # [5, 4, 3, 2, 1]

# Use in loops
for (i in range(3)) {
    log("Iteration ${i}")
}
```

### String Functions

#### `split(text, [delimiter])` - Split String

Splits string into list using delimiter:

```cy
# Default space delimiter
words = split("hello world")      # ["hello", "world"]

# Custom delimiter
parts = split("a,b,c", ",")       # ["a", "b", "c"]
path = split("/home/user/docs", "/")  # ["", "home", "user", "docs"]

# CSV parsing
csv_line = "Alice,30,Engineer"
fields = split(csv_line, ",")     # ["Alice", "30", "Engineer"]
```

#### `replace(text, old, new)` - Replace Substring

Replaces all occurrences of substring:

```cy
# Basic replacement
text = replace("hello world", "world", "there")  # "hello there"

# Replace all occurrences
text = replace("foo foo foo", "foo", "bar")  # "bar bar bar"

# Clean data
email = replace(user_input, " ", "")  # Remove spaces
```

#### `trim(text)` - Remove Whitespace

Removes leading and trailing whitespace:

```cy
# Clean input
name = trim("  Alice  ")          # "Alice"
data = trim("\n\tvalue\t\n")      # "value"

# Process user input
username = trim(input.username)
if (username == "") {
    return "Error: Username required"
}
```

#### `regex_match(pattern, text)` - Test Regex Match

Checks if regex pattern matches text:

<!-- cy-test: expect-error -->
```cy
# Validate format
has_digits = regex_match(r"\d+", "abc123")  # True
is_email = regex_match(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", email)

# Pattern detection
if (regex_match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", input.value)) {
    return "Detected IP address"
}
```

#### `regex_extract(pattern, text)` - Extract Matching Text

Extracts first match of regex pattern:

<!-- cy-test: expect-error -->
```cy
# Extract numbers
price = regex_extract(r"\d+", "Price: 123 dollars")  # "123"

# Extract with groups (returns first group)
username = regex_extract(r"User: (\w+)", "User: alice")  # "alice"

# Extract domain
domain = regex_extract(r"@([\w.-]+)", "user@example.com")  # "example.com"

# Safe extraction (returns "" if no match)
result = regex_extract(r"\d+", "no numbers")  # ""
```

### Array Functions

#### `reverse(items)` - Reverse List Order

Returns new list with items in reverse order:

```cy
# Reverse numbers
nums = reverse([1, 2, 3])         # [3, 2, 1]

# Reverse strings
tags = reverse(["a", "b", "c"])   # ["c", "b", "a"]

# Process in reverse
for (item in reverse(queue)) {
    log("Processing: ${item}")
}
```

#### `sort(items)` - Sort List

Returns new sorted list in ascending order:

```cy
# Sort numbers
nums = sort([3, 1, 2])            # [1, 2, 3]

# Sort strings
names = sort(["charlie", "alice", "bob"])  # ["alice", "bob", "charlie"]

# Sort scores
scores = [95, 87, 92]
ranked = sort(scores)             # [87, 92, 95]
```

### Math Functions

#### `abs(value)` - Absolute Value

Returns absolute value of a number:

```cy
# Positive numbers
val1 = abs(5)                     # 5
val2 = abs(-5)                    # 5

# Calculate distance
distance = abs(x2 - x1)

# Calculate difference
diff = abs(expected - actual)
```

#### `min(items)` - Minimum Value

Returns minimum value from list:

```cy
# Find minimum
lowest = min([5, 2, 8, 1, 9])     # 1

# Find lowest score
scores = [87, 92, 78, 95]
lowest_score = min(scores)        # 78

# With negative numbers
min_temp = min([-5, -2, -10])     # -10
```

#### `max(items)` - Maximum Value

Returns maximum value from list:

```cy
# Find maximum
highest = max([5, 2, 8, 1, 9])    # 9

# Find highest score
scores = [87, 92, 78, 95]
highest_score = max(scores)       # 95

# Risk calculation
max_risk = max(risk_scores)
```

#### `round(value, [decimals])` - Round Number

Rounds number to specified decimal places:

```cy
# Round to integer
val1 = round(3.14159)             # 3.0

# Round to decimals
pi = round(3.14159, 2)            # 3.14
price = round(19.99, 1)           # 20.0

# Financial calculations
total = round(sum(prices) * 1.0825, 2)  # Round to cents
```

### Collection & Utility Functions

#### `unique(items)` - Remove Duplicates

Removes duplicate values from a list, preserving first-occurrence order:

```cy
# Basic deduplication
ips = unique(["1.1.1.1", "8.8.8.8", "1.1.1.1"])  # ["1.1.1.1", "8.8.8.8"]

# Deduplicate numbers
nums = unique([1, 2, 2, 3, 1])                     # [1, 2, 3]

# Empty list
empty = unique([])                                   # []
```

#### `flatten(items)` - Flatten Nested Lists

Flattens one level of nesting:

```cy
# Basic flatten
flat = flatten([[1, 2], [3, 4]])        # [1, 2, 3, 4]

# Mixed nested and non-nested
flat = flatten([[1], 2, [3]])           # [1, 2, 3]

# Only one level deep
flat = flatten([[1, [2, 3]], [4]])      # [1, [2, 3], 4]
```

#### `type_of(value)` - Runtime Type Introspection

Returns the type of a value as a string:

```cy
t = type_of("hello")          # "string"
t = type_of(42)                # "number"
t = type_of(True)              # "boolean"
t = type_of([1, 2])            # "list"
t = type_of({"a": 1})          # "dict"
t = type_of(null)              # "null"

# Branch on type at runtime
val = input.data ?? ""
if (type_of(val) == "string") {
    result = "Got a string"
} elif (type_of(val) == "list") {
    result = "Got a list"
}
```

#### `slice(items, start, [end])` - Sub-range of List or String

Returns a sub-range. Negative indices count from end:

```cy
# List slicing
middle = slice([1, 2, 3, 4, 5], 1, 3)   # [2, 3]
rest = slice([1, 2, 3, 4, 5], 2)         # [3, 4, 5]
last_two = slice([1, 2, 3, 4, 5], -2)    # [4, 5]

# String slicing
word = slice("hello world", 0, 5)         # "hello"
suffix = slice("hello world", 6)           # "world"
```

#### `index_of(items, value)` - Find First Index

Returns the first index of a value, or -1 if not found:

```cy
# List search
idx = index_of([10, 20, 30], 20)          # 1
idx = index_of([10, 20, 30], 99)          # -1

# String search
pos = index_of("hello world", "world")    # 6
pos = index_of("hello", "xyz")            # -1
```

#### `base64_encode(text)` / `base64_decode(text)` - Base64 Encoding

```cy
# Encode
encoded = base64_encode("user:pass")      # "dXNlcjpwYXNz"

# Decode
decoded = base64_decode("aGVsbG8=")       # "hello"

# Roundtrip
original = "secret data"
decoded = base64_decode(base64_encode(original))  # "secret data"

# Security: decode suspicious payload
payload = base64_decode(suspicious_b64)
```

## Tool Call Syntax

### Positional Arguments

```cy
# Standard function call with positional args
sum = add(5, 3)
result = multiply(10, 20)

# Multiple positional args
formatted = format(data, "json", 2)
```

### Named Arguments

Use `=` for named arguments (not `:`):

```cy
# ✅ CORRECT - use = for named args
result = calculate(amount=100, rate=0.05)
data = fetch_api(url="api.com", timeout=30)
```

<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - don't use : (that's for dicts)
result = calculate(amount: 100, rate: 0.05)  # ERROR
```

### Mixed Arguments

Positional arguments must come before named arguments (like Python).
Once a named argument appears, all remaining must be named:

```cy
# ✅ CORRECT - positional first, then named
result = calculate(100, rate=0.05)

# ✅ CORRECT - all positional
result = calculate(100, 0.05)

# ✅ CORRECT - all named
result = calculate(amount=100, rate=0.05)

# ✅ CORRECT - named args can be in any order after positional
result = process("data", mode="fast", threshold=0.8)
```

<!-- cy-test: expect-error -->
```cy
# ❌ WRONG - named args must come AFTER positional
result = calculate(amount=100, 0.05)
```

## Integration Tool Patterns

### App Tools (Your Integration Tools)

```cy
# VirusTotal integration
vt_data = app::virustotal::ip_reputation(ip_address="8.8.8.8")
malicious = vt_data.malicious_score

# Shodan integration
shodan_data = app::shodan::host_lookup(ip="8.8.8.8", detailed=True)
ports = shodan_data.ports

# Custom security tools
analysis = app::security::analyze_ip(
    ip="192.168.1.1",
    context="internal_network"
)
```

### MCP Tools (Model Context Protocol)

MCP tools require async setup and always use FQN:

```cy
# Math operations via MCP
result = mcp::demo::add(a=10, b=15)
product = mcp::demo::multiply(a=5, b=3)

# External API via MCP
weather = mcp::weather::get_forecast(city="San Francisco")
```

## Common Tool Patterns

### API Call Workflow

```cy
# Parallel API calls with for-in
urls = ["api.com/user1", "api.com/user2", "api.com/user3"]
responses = []

for (url in urls) {
    response = app::http::fetch(url=url, timeout=10)
    responses = responses + [response]
}

return {"results": responses, "count": len(responses)}
```

### Data Transformation Pipeline

```cy
# Multi-step transformation using tools
raw_data = input["data"]

# Step 1: Parse JSON
parsed = from_json(raw_data)

# Step 2: Process with custom tool
processed = app::processor::transform(data=parsed, mode="clean")

# Step 3: Format output
formatted = to_json(processed, 2)

return formatted
```

### Security Analysis Pattern

```cy
# Security workflow with multiple integrations
ip = input["ip_address"]

# Get reputation from VirusTotal
vt_result = app::virustotal::ip_reputation(ip_address=ip)

# Get context from Shodan
shodan_result = app::shodan::host_lookup(ip=ip)

# Combine results
analysis = {
    "ip": ip,
    "malicious_score": vt_result.malicious_score,
    "open_ports": shodan_result.ports,
    "risk_level": if (vt_result.malicious_score > 7) { "HIGH" } else { "LOW" }
}

return analysis
```

### Error-Safe Tool Calls

```cy
# Handle tool failures gracefully
results = []

for (target in targets) {
    try {
        result = app::scanner::scan(target=target, depth=2)
        results = results + [result]
    } catch (e) {
        log("Failed to scan ${target}: ${e}")
        results = results + [{"target": target, "error": "${e}"}]
    }
}

return {"results": results}
```

## Tool Registration (Python Side)

### Registering Custom Tools

```python
from cy_language import Cy

# Define custom function
def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"

# Register with FQN
tools = {
    "app::custom::greet": greet
}

cy = Cy(tools=tools)

script = '''
message = app::custom::greet(name="Alice", greeting="Hi")
return message
'''

result = cy.run(script)  # "Hi, Alice!"
```

### Integration Tool Registration

```python
# Register VirusTotal integration
def virustotal_ip_reputation(ip_address: str) -> dict:
    # Call VirusTotal API
    return {
        "ip": ip_address,
        "malicious_score": 8,
        "reputation": "suspicious"
    }

app_tools = {
    "app::virustotal::ip_reputation": virustotal_ip_reputation
}

cy = Cy(check_types=True, tools=app_tools)
```

## Quick Reference

### Original Functions (10)

| Function | Parameters | Returns | Example |
|----------|------------|---------|---------|
| `len(arg)` | string/list/dict | number | `len([1,2,3])` → 3 |
| `sum(items)` | list of numbers | number | `sum([1,2,3])` → 6 |
| `str(value)` | any | string | `str(42)` → "42" |
| `int(value)` | string/number | number | `int("42")` → 42 |
| `from_json(text)` | string | object/array | `from_json('{"a":1}')` |
| `to_json(data, indent?)` | object/array, number? | string | `to_json(data, 2)` |
| `uppercase(text)` | string | string | `uppercase("hi")` → "HI" |
| `lowercase(text)` | string | string | `lowercase("HI")` → "hi" |
| `join(items, sep?)` | list, string? | string | `join(["a","b"], "/")` |
| `log(message)` | string | void | `log("Processing...")` |

### Extended Functions (20)

| Function | Parameters | Returns | Example |
|----------|------------|---------|---------|
| **Type Conversion** |
| `num(value)` | any | number | `num("3.14")` → 3.14 |
| `bool(value)` | any | boolean | `bool("true")` → True |
| **Time** |
| `now(timezone?)` | string? | string | `now()` → "2025-10-31T14:30:00Z" |
| **Iteration** |
| `range(end)` / `range(start, end, step?)` | number, number?, number? | list | `range(5)` → [0,1,2,3,4] |
| **String** |
| `split(text, delim?)` | string, string? | list | `split("a,b", ",")` → ["a","b"] |
| `replace(text, old, new)` | string, string, string | string | `replace("hi", "i", "o")` → "ho" |
| `trim(text)` | string | string | `trim("  hi  ")` → "hi" |
| `regex_match(pat, text)` | string, string | boolean | `regex_match(r"\d+", "abc123")` → True |
| `regex_extract(pat, text)` | string, string | string | `regex_extract(r"\d+", "abc123")` → "123" |
| **Array** |
| `reverse(items)` | list | list | `reverse([1,2,3])` → [3,2,1] |
| `sort(items)` | list | list | `sort([3,1,2])` → [1,2,3] |
| **Math** |
| `abs(value)` | number | number | `abs(-5)` → 5 |
| `min(items)` | list | number | `min([5,2,8])` → 2 |
| `max(items)` | list | number | `max([5,2,8])` → 8 |
| `round(value, dec?)` | number, number? | number | `round(3.14, 1)` → 3.1 |
| **URL** |
| `url_encode(text)` | string | string | `url_encode("a b")` → "a+b" |
| `url_decode(text)` | string | string | `url_decode("a+b")` → "a b" |
| **Dict** |
| `keys(dict)` | dict | list | `keys({"a":1})` → ["a"] |
| `values(dict)` | dict | list | `values({"a":1})` → [1] |

### Additional Functions (15)

| Function | Parameters | Returns | Example |
|----------|------------|---------|---------|
| **Time Arithmetic** (see `reference/time-arithmetic.md`) |
| `add_duration(ts, dur)` | string, string | string | `add_duration(now(), "2h")` |
| `subtract_duration(ts, dur)` | string, string | string | `subtract_duration(now(), "30m")` |
| `duration_between(ts1, ts2)` | string, string | number | `duration_between(start, end)` |
| `parse_duration(text)` | string | number | `parse_duration("2h30m")` → 9000 |
| `format_duration(secs)` | number | string | `format_duration(9000)` → "2h30m" |
| `timestamp_compare(ts1, ts2)` | string, string | number | `timestamp_compare(a, b)` → -1/0/1 |
| **Epoch Conversion** |
| `from_epoch(secs)` | number | string | `from_epoch(1700000000)` |
| `to_epoch(ts)` | string | number | `to_epoch(now())` |
| **Network** |
| `is_ipv4(text)` | string | boolean | `is_ipv4("8.8.8.8")` → True |
| `is_ipv6(text)` | string | boolean | `is_ipv6("::1")` → True |
| `is_ip(text)` | string | boolean | `is_ip("8.8.8.8")` → True |
| **String Utilities** |
| `strip_markdown(text)` | string | string | `strip_markdown("**bold**")` → "bold" |
| `startswith(text, prefix)` | string, string | boolean | `startswith("hello", "he")` → True |
| `endswith(text, suffix)` | string, string | boolean | `endswith("hello", "lo")` → True |
| **List Utilities** |
| `take(items, n)` | list, number | list | `take([1,2,3], 2)` → [1,2] |

### Collection & Utility Functions (7)

| Function | Parameters | Returns | Example |
|----------|------------|---------|---------|
| **Collections** |
| `unique(items)` | list | list | `unique([1,2,2,3])` → [1,2,3] |
| `flatten(items)` | list | list | `flatten([[1,2],[3]])` → [1,2,3] |
| `slice(items, start, end?)` | list/string, number, number? | list/string | `slice([1,2,3,4], 1, 3)` → [2,3] |
| `index_of(items, value)` | list/string, any | number | `index_of([10,20,30], 20)` → 1 |
| **Type Introspection** |
| `type_of(value)` | any | string | `type_of("hi")` → "string" |
| **Encoding** |
| `base64_encode(text)` | string | string | `base64_encode("hello")` → "aGVsbG8=" |
| `base64_decode(text)` | string | string | `base64_decode("aGVsbG8=")` → "hello" |

## Namespace Prefixes

| Prefix | Meaning | Example | Registration |
|--------|---------|---------|--------------|
| `native::tools::` | Built-in functions | `native::tools::len()` | Automatic |
| `app::` | Your app integrations | `app::virustotal::ip_reputation()` | Via `tools=` |
| `arc::` | Archetype tools | `arc::processor::transform()` | Via app manager |
| `mcp::` | MCP protocol tools | `mcp::demo::add()` | Via MCP setup |
| (no prefix) | Short name (if unique) | `len()`, `log()` | Resolves at compile time |
