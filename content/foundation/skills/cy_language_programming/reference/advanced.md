# Cy Language Advanced Features

Advanced topics including parallel execution, MCP integration, complex workflows, and performance optimization.

## Parallel Processing with For-In Loops

One of Cy's most powerful features is **automatic parallelization** of for-in loops when iterations are independent.

### How It Works

```cy
# These API calls automatically run in parallel
api_endpoints = ["users", "posts", "comments", "likes"]
api_results = []

# Each iteration is independent - executes concurrently!
for (endpoint in api_endpoints) {
    data = fetch_api(endpoint)  # All 4 calls run at once
    api_results = api_results + [data]
}

return api_results  # Collected in order
```

**Key Points:**
- Iterations that don't depend on each other run **concurrently**
- Results are still collected in **original order**
- No special syntax needed - the engine detects parallelizable loops
- Works with tool calls, API requests, and data transformations

### Parallel Data Enrichment

```cy
# Process multiple items with independent transformations
items = [
    {"id": 1, "value": 100},
    {"id": 2, "value": 200},
    {"id": 3, "value": 300}
]

enriched_items = []
for (item in items) {
    # Both calls run independently for each item
    details = get_item_details(item.id)  # API call 1
    score = calculate_score(item.value)   # API call 2

    enriched = {
        "id": item.id,
        "value": item.value,
        "details": details,
        "score": score
    }
    enriched_items = enriched_items + [enriched]
}

return enriched_items
```

### When Parallelization Works

✅ **Parallelizable** - Each iteration is self-contained:
```cy
# Process independent items
for (url in urls) {
    response = fetch(url)  # No dependency between URLs
    results = results + [response]
}

# Transform independent data
for (user in users) {
    enriched = enrich_user_data(user)  # Each user processed independently
    enriched_users = enriched_users + [enriched]
}
```

❌ **Not parallelizable** - Iterations depend on previous results:
```cy
# Sequential - each iteration needs the previous result
total = 0
for (item in items) {
    total = total + item  # Depends on previous total
}

# Sequential - building on previous state
result = initial_value
for (step in steps) {
    result = process(result, step)  # Each step needs previous result
}
```

### Performance Benefits

```cy
# Without parallelization: 4 seconds (4 × 1s sequential)
# With parallelization: 1 second (4 × 1s concurrent)

ip_addresses = ["8.8.8.8", "1.1.1.1", "208.67.222.222", "9.9.9.9"]
reputation_reports = []

for (ip in ip_addresses) {
    # Each API call takes ~1 second
    report = app::virustotal::ip_reputation(ip_address=ip)
    reputation_reports = reputation_reports + [report]
}
# Total time: ~1 second instead of ~4 seconds!
```

## MCP Integration

Cy supports the Model Context Protocol (MCP) for calling external tools and services.

### Enabling MCP

**Important:** MCP requires async initialization using `Cy.create_async()` instead of the regular `Cy()` constructor.

```python
from cy_language import Cy

# Create Cy instance with MCP servers configured
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
    }
)

# Run scripts with async
output = await cy.run_async(script)
```

### MCP Tool Calls

MCP tools **always use Fully Qualified Names** with the `mcp::` namespace:

```cy
# Math operations via MCP
result = mcp::demo::add(a=10, b=15)
product = mcp::demo::multiply(a=5, b=3)

# Security analysis via MCP
vt_report = mcp::virustotal::virustotal_ip_reputation(ip="8.8.8.8")
malicious_count = vt_report.malicious
total_engines = vt_report.total

# Weather data
forecast = mcp::weather::get_forecast(city="San Francisco")
temperature = forecast.temp
```

### MCP Namespace Pattern

| Namespace | Description | Example |
|-----------|-------------|---------|
| `mcp::demo::*` | Demo/test tools | `mcp::demo::add(a=1, b=2)` |
| `mcp::virustotal::*` | VirusTotal integration | `mcp::virustotal::ip_reputation(...)` |
| `mcp::weather::*` | Weather services | `mcp::weather::get_forecast(...)` |

**Important:** MCP calls require async setup with `Cy.create_async()` and must use explicit FQN (no short names).

### Complete MCP Example

```python
from cy_language import Cy

async def main():
    # Create Cy with MCP servers
    cy = await Cy.create_async(
        mcp_servers={
            "demo": {
                "base_url": "http://localhost:8000",
                "mcp_id": "demo"
            }
        }
    )

    # Cy script using MCP tools
    script = """
    # Call MCP tools with mcp:: namespace
    sum = mcp::demo::add(a=10, b=20)
    product = mcp::demo::multiply(a=4, b=5)

    # MCP tools work in string interpolation
    text = "Hello World"
    length = mcp::demo::text_length(text=text)

    output = "Sum: ${sum}, Product: ${product}, Length: ${length}"
    return output
    """

    # Run async
    result = await cy.run_async(script)
    print(result)
    # Output: "Sum: 30, Product: 20, Length: 11"

# Run with asyncio
import asyncio
asyncio.run(main())
```

## Complex Workflow Patterns

### Multi-Source Data Aggregation

```cy
# Gather data from multiple sources in parallel
ip = input.ip_address

# These calls run concurrently
vt_data = app::virustotal::ip_reputation(ip_address=ip)
shodan_data = app::shodan::host_lookup(ip=ip)
geo_data = app::geoip::lookup(ip=ip)

# Aggregate results
risk_score = app::security::calculate_risk(
    malicious_score=vt_data.malicious_score,
    open_ports=len(shodan_data.ports),
    country_risk=geo_data.country_risk
)

# Build comprehensive report
report = {
    "ip": ip,
    "threat_intel": vt_data,
    "infrastructure": shodan_data,
    "location": geo_data,
    "risk_assessment": {
        "score": risk_score,
        "severity": if (risk_score > 70) { "HIGH" } else { "MEDIUM" }
    }
}

return report
```

### Conditional Pipeline

```cy
# Multi-stage processing with conditional logic
data = input.raw_data

# Stage 1: Validate
if (len(data) == 0) {
    return {"error": "Empty data"}
}

# Stage 2: Parse
try {
    parsed = from_json(data)
} catch (e) {
    return {"error": "Invalid JSON: ${e}"}
}

# Stage 3: Enrich (parallel)
enriched_items = []
for (item in parsed.items) {
    enriched = app::enrichment::enhance(item)
    enriched_items = enriched_items + [enriched]
}

# Stage 4: Analyze
analysis = app::analytics::analyze(enriched_items)

# Stage 5: Format output
if (analysis.confidence > 0.8) {
    return {
        "status": "success",
        "data": enriched_items,
        "analysis": analysis,
        "recommendation": "PROCEED"
    }
} else {
    return {
        "status": "warning",
        "data": enriched_items,
        "analysis": analysis,
        "recommendation": "MANUAL_REVIEW"
    }
}
```

### Error-Resilient Batch Processing

```cy
# Process multiple items with graceful error handling
targets = input.targets
results = []
errors = []

for (target in targets) {
    try {
        # Try primary method
        result = app::scanner::deep_scan(
            target=target,
            depth=3,
            timeout=30
        )
        results = results + [result]

    } catch (e) {
        # Primary failed, try fallback
        try {
            result = app::scanner::quick_scan(target=target, depth=1)
            results = results + [result]
            log("Used fallback for ${target}")

        } catch (e2) {
            # Both failed, log and continue
            error_record = {
                "target": target,
                "error": "${e2}",
                "timestamp": app::utils::now()
            }
            errors = errors + [error_record]
            log("Failed to scan ${target}: ${e2}")
        }
    }
}

# Return comprehensive results
return {
    "successful": len(results),
    "failed": len(errors),
    "results": results,
    "errors": errors
}
```

## Advanced Data Manipulation

### Indexed Assignment

Modify dictionaries and lists in place:

```cy
# Build dictionary dynamically
ip_risk_scores = {}
ip_risk_scores["8.8.8.8"] = 85
ip_risk_scores["1.1.1.1"] = 12

# Variable keys
suspicious_ips = ["8.8.8.8", "192.168.1.1"]
for (ip in suspicious_ips) {
    vt_data = app::virustotal::ip_reputation(ip_address=ip)
    ip_risk_scores[ip] = vt_data.malicious_score
}

# Nested updates
config = {"settings": {}}
config["settings"]["timeout"] = 30
config["settings"]["retries"] = 3

# List updates
items = ["a", "b", "c"]
items[0] = "x"  # ["x", "b", "c"]
items[2] = "z"  # ["x", "b", "z"]
```

### Dynamic Data Structures

```cy
# Build complex structures dynamically
report = {}
report["metadata"] = {
    "timestamp": app::utils::now(),
    "version": "2.0",
    "analyst": input.analyst_name
}

# Add findings from analysis
findings = []
for (indicator in input.indicators) {
    analysis = app::threat_intel::analyze(indicator)

    finding = {
        "indicator": indicator,
        "type": analysis.type,
        "severity": analysis.severity,
        "context": analysis.context
    }
    findings = findings + [finding]
}

report["findings"] = findings
report["summary"] = {
    "total_indicators": len(findings),
    "high_severity": len([f for(f in findings) if(f.severity == "HIGH")])
}

return report
```

## Workflow Composition Patterns

### Task Chaining

```cy
# Chain multiple processing steps
# Task A output becomes Task B input

# Task A: Gather raw data
raw_indicators = []
for (source in input.sources) {
    data = app::sources::fetch(source)
    raw_indicators = raw_indicators + data.indicators
}

task_a_output = {
    "indicators": raw_indicators,
    "count": len(raw_indicators)
}

# Task B: Enrich indicators (uses Task A output)
enriched_indicators = []
for (indicator in task_a_output.indicators) {
    enriched = app::enrichment::enrich(
        indicator=indicator,
        depth="full"
    )
    enriched_indicators = enriched_indicators + [enriched]
}

task_b_output = {
    "indicators": enriched_indicators,
    "enrichment_status": "complete"
}

# Task C: Analyze enriched data (uses Task B output)
analysis = app::analytics::comprehensive_analysis(
    indicators=task_b_output.indicators
)

# Final output
return {
    "pipeline": "A -> B -> C",
    "analysis": analysis,
    "metadata": {
        "raw_count": task_a_output.count,
        "enriched_count": len(task_b_output.indicators)
    }
}
```

### Parallel Fan-Out / Sequential Fan-In

```cy
# Fan-out: Process multiple items in parallel
ip_addresses = input.ip_list

# Parallel phase - all reputation checks run concurrently
reputation_data = []
for (ip in ip_addresses) {
    vt_data = app::virustotal::ip_reputation(ip_address=ip)
    reputation_data = reputation_data + [vt_data]
}

# Fan-in: Aggregate results sequentially
total_malicious = 0
total_suspicious = 0
total_clean = 0

for (data in reputation_data) {
    if (data.malicious_score >= 7) {
        total_malicious = total_malicious + 1
    } elif (data.malicious_score >= 3) {
        total_suspicious = total_suspicious + 1
    } else {
        total_clean = total_clean + 1
    }
}

# Aggregate summary
return {
    "total_analyzed": len(ip_addresses),
    "malicious": total_malicious,
    "suspicious": total_suspicious,
    "clean": total_clean,
    "risk_percentage": (total_malicious + total_suspicious) * 100 / len(ip_addresses)
}
```

## Performance Optimization

### Minimize Sequential Dependencies

```cy
# ❌ Slow - sequential processing
result1 = fetch_data_a()
result2 = fetch_data_b()  # Waits for result1 even though independent
result3 = fetch_data_c()  # Waits for result2

# ✅ Fast - parallel processing with for-in
endpoints = ["data_a", "data_b", "data_c"]
results = []
for (endpoint in endpoints) {
    result = fetch_data(endpoint)  # All run concurrently
    results = results + [result]
}
```

### Batch Processing

```cy
# Process large datasets efficiently
all_items = input.large_dataset  # 10,000 items

# Process in parallel batches
batch_size = 100
batch_results = []

# Split into batches (sequential loop for batching)
batch_count = len(all_items) / batch_size
batch_index = 0
while (batch_index < batch_count) {
    # Get batch
    start = batch_index * batch_size
    end = start + batch_size
    batch = []  # Would slice in real implementation

    # Process batch items in parallel
    batch_items = []
    for (item in batch) {
        processed = app::processor::process(item)
        batch_items = batch_items + [processed]
    }

    batch_results = batch_results + batch_items
    batch_index = batch_index + 1
}

return {
    "processed": len(batch_results),
    "batches": batch_count
}
```

### Conditional Tool Execution

```cy
# Only call expensive tools when necessary
ip = input.ip_address

# Quick local check first
is_private = app::utils::is_private_ip(ip)

# Only call external APIs for public IPs
if (not is_private) {
    # These expensive calls only happen when needed
    vt_data = app::virustotal::ip_reputation(ip_address=ip)
    shodan_data = app::shodan::host_lookup(ip=ip)

    return {
        "type": "public",
        "reputation": vt_data,
        "infrastructure": shodan_data
    }
} else {
    return {
        "type": "private",
        "note": "Skipped external lookups for private IP"
    }
}
```

## Advanced Error Handling

### Retry Logic

```cy
# Retry failed operations with backoff
max_retries = 3
retry_count = 0
result = ""

while (retry_count < max_retries) {
    try {
        result = app::api::fetch_data(
            url=input.api_url,
            timeout=30
        )
        return result  # Success - exit early

    } catch (e) {
        retry_count = retry_count + 1
        log("Attempt ${retry_count} failed: ${e}")

        if (retry_count >= max_retries) {
            return {
                "error": "Max retries exceeded",
                "last_error": "${e}",
                "attempts": retry_count
            }
        }

        # Continue to next retry
    }
}
```

### Error Aggregation

```cy
# Collect all errors without stopping
operations = [
    {"type": "fetch", "url": "api.com/users"},
    {"type": "fetch", "url": "api.com/posts"},
    {"type": "process", "data": "complex_data"}
]

successful = []
failed = []

for (op in operations) {
    try {
        if (op.type == "fetch") {
            result = app::http::fetch(url=op.url)
        } else {
            result = app::processor::process(data=op.data)
        }

        successful = successful + [{
            "operation": op,
            "result": result
        }]

    } catch (e) {
        failed = failed + [{
            "operation": op,
            "error": "${e}"
        }]
    }
}

# Return comprehensive results
return {
    "summary": {
        "total": len(operations),
        "successful": len(successful),
        "failed": len(failed)
    },
    "successful_operations": successful,
    "failed_operations": failed
}
```

## Real-World Security Analysis Example

```cy
# Advanced security analysis with dynamic risk scoring
suspicious_ip = input.ip
alert_context = input.context

# Initialize risk tracking
ip_risk_scores = {}
ip_risk_scores[suspicious_ip] = 0

# Parallel threat intelligence gathering
vt_report = app::virustotal::ip_reputation(ip_address=suspicious_ip)
shodan_report = app::shodan::host_lookup(ip=suspicious_ip)
geo_data = app::geoip::lookup(ip=suspicious_ip)

# Calculate reputation risk
malicious_count = vt_report.malicious
total_engines = vt_report.total
detection_ratio = 0
if (total_engines > 0) {
    detection_ratio = malicious_count / total_engines
}

reputation_score = detection_ratio * 100

# Calculate infrastructure risk
open_ports = len(shodan_report.ports)
vulnerable_services = len(shodan_report.vulnerabilities)
infrastructure_score = (open_ports * 2) + (vulnerable_services * 10)

# Calculate geographic risk
high_risk_countries = ["XX", "YY", "ZZ"]
country_code = geo_data.country_code
geo_risk = 0
for (risky_country in high_risk_countries) {
    if (country_code == risky_country) {
        geo_risk = 25
    }
}

# Composite risk score
total_risk = reputation_score + infrastructure_score + geo_risk
ip_risk_scores[suspicious_ip] = total_risk

# Determine threat level and action
threat_level = "Low"
recommended_action = "MONITOR"

if (total_risk >= 80) {
    threat_level = "Critical"
    recommended_action = "BLOCK_IMMEDIATELY"
} elif (total_risk >= 50) {
    threat_level = "High"
    recommended_action = "INVESTIGATE"
} elif (total_risk >= 25) {
    threat_level = "Medium"
    recommended_action = "MONITOR_CLOSELY"
}

# Comprehensive output
return {
    "ip_address": suspicious_ip,
    "analysis_timestamp": app::utils::now(),
    "threat_assessment": {
        "level": threat_level,
        "total_risk_score": total_risk,
        "component_scores": {
            "reputation": reputation_score,
            "infrastructure": infrastructure_score,
            "geographic": geo_risk
        }
    },
    "intelligence": {
        "virustotal": {
            "malicious_detections": malicious_count,
            "total_engines": total_engines,
            "detection_ratio": detection_ratio
        },
        "infrastructure": {
            "open_ports": open_ports,
            "vulnerabilities": vulnerable_services
        },
        "location": {
            "country": geo_data.country_name,
            "country_code": country_code,
            "is_high_risk_region": geo_risk > 0
        }
    },
    "recommended_action": recommended_action,
    "alert_context": alert_context
}
```

## Best Practices

### ✅ Do This

1. **Use for-in for parallel work**: Maximize performance with independent iterations
2. **Early validation**: Check inputs before expensive operations
3. **Graceful degradation**: Use try/catch with fallbacks
4. **Log extensively**: Use `log()` for debugging and audit trails
5. **Structure data early**: Build clear data structures at the start
6. **Minimize sequential dependencies**: Design workflows for parallelism
7. **Use indexed assignment**: Build dynamic structures efficiently

### ❌ Avoid This

1. **Don't use while when for-in works**: Loses parallelization opportunity
2. **Don't create deep nesting**: Break into smaller functions/tasks
3. **Don't ignore errors silently**: Always log or handle errors
4. **Don't repeat tool calls**: Cache results when possible
5. **Don't build strings with concatenation**: Use interpolation instead
6. **Don't make sequential calls for independent data**: Use for-in loops

## Quick Reference

### Parallel Processing

```cy
# Automatic parallelization
for (item in items) {
    result = independent_operation(item)
    results = results + [result]
}
```

### MCP Tools

```cy
# Always use FQN with mcp:: namespace
result = mcp::service::function(arg=value)
```

### Error Handling

```cy
try {
    risky_operation()
} catch (e) {
    log("Error: ${e}")
    fallback_operation()
}
```

### Dynamic Data

```cy
# Indexed assignment
dict[key] = value
list[index] = item
```

### Workflow Composition

```cy
# Chain tasks: A → B → C
output_a = task_a()
output_b = task_b(output_a)
output_c = task_c(output_b)
return output_c
```
