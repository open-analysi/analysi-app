# Task Composition: Using task_run() in Cy Scripts

## Understanding task_run() Return Value

When calling `task_run()`, the result is a complete execution object with this structure:

```json
{
  "status": "succeeded" | "failed",
  "output": <actual_task_output>,
  "execution_time": <float>,
  "error": <error_message_if_failed>
}
```

## Common Issues and Solutions

### Issue: Getting [object Object] when returning task_run directly

**Problem:**
```cy
return task_run("some_task", {})  # May show as [object Object]
```

**Solutions:**

### Solution 1: Return just the output field (RECOMMENDED)
```cy
$result = task_run("some_task", {})
output = $result["output"]  # Returns the actual task data
```

### Solution 2: Use JSON filter for serialization
```cy
$x = task_run("some_task", {})
return {"result": "${x|json}"}  # Returns a JSON string representation
```

### Solution 3: Build a custom response
```cy
$result = task_run("child_task", {})

# Check if task succeeded
if ($result["status"] == "succeeded") {
    return {
        "success": true,
        "data": $result["output"],
        "execution_time": $result["execution_time"]
    }
} else {
    return {
        "success": false,
        "error": $result["error"]
    }
}
```

## Complete Examples

### Example 1: Simple task composition
```cy
# Parent task that uses a child task
# cy_name: data_processor

$result = task_run("data_generator", {})
$data = $result["output"]

# Process the data
$processed = {
    "original_value": $data["value"],
    "doubled_value": $data["value"] * 2,
    "timestamp": $data["timestamp"]
}

output = $processed
```

### Example 2: Calling Splunk task and handling results
```cy
# Call the Splunk task
$splunk_result = task_run("splunk_event_retrieval", {})

# Check if it succeeded
if ($splunk_result["status"] == "succeeded") {
    # Extract the actual output
    $splunk_data = $splunk_result["output"]

    # Use the data
    return {
        "events": $splunk_data["events"],
        "summary": $splunk_data["summary"],
        "query_used": $splunk_data["spl_query"]
    }
} else {
    # Handle failure
    return {
        "error": "Splunk task failed",
        "details": $splunk_result["error"]
    }
}
```

### Example 3: Chaining multiple tasks
```cy
# Step 1: Get data from first task
$step1_result = task_run("fetch_data", {})
$data = $step1_result["output"]

# Step 2: Process with second task
$step2_result = task_run("process_data", {"input": $data})
$processed = $step2_result["output"]

# Step 3: Generate report with third task
$step3_result = task_run("generate_report", {"data": $processed})

# Return final result
output = $step3_result["output"]
```

### Example 4: Error handling with nested calls
```cy
# Try to run a task
$result = task_run("risky_task", {"param": "value"})

if ($result["status"] == "failed") {
    # Try fallback task
    $fallback = task_run("safe_task", {})

    if ($fallback["status"] == "succeeded") {
        return {
            "source": "fallback",
            "data": $fallback["output"]
        }
    } else {
        return {
            "error": "Both primary and fallback tasks failed",
            "primary_error": $result["error"],
            "fallback_error": $fallback["error"]
        }
    }
} else {
    return {
        "source": "primary",
        "data": $result["output"]
    }
}
```

### Example 5: Parallel task execution pattern
```cy
# Execute multiple enrichment tasks
$ip_enrichment = task_run("ip_reputation_enrichment", {"source_ip": input["ip"]})
$user_enrichment = task_run("user_privilege_enrichment", {"username": input["user"]})

# Combine results
return {
    "alert_id": input["alert_id"],
    "ip_data": $ip_enrichment["output"],
    "user_data": $user_enrichment["output"]
}
```

## Key Takeaways

1. **Always extract the output field** when you need the actual task data: `$result["output"]`

2. **Check the status** before using the output: `if ($result["status"] == "succeeded")`

3. **Use the |json filter** when you need a JSON string: `"${result|json}"`

4. **Handle errors gracefully** - the parent task succeeds even if the child fails

5. **Remember recursion limits** - maximum depth is 10 levels

## Debugging Tips

If you're getting unexpected output:

1. First store the result in a variable:
   ```cy
   $result = task_run("task_name", {})
   ```

2. Check what you actually got:
   ```cy
   $debug_info = {
       "status": $result["status"],
       "has_output": $result["output"] != null,
       "has_error": $result["error"] != null
   }
   output = $debug_info
   ```

3. Then access the specific field you need:
   ```cy
   output = $result["output"]  # For the actual data
   ```

## Best Practices

1. **Use meaningful variable names**: `$enrichment_result` instead of `$r`
2. **Check status for critical operations**: Don't assume tasks always succeed
3. **Provide fallbacks**: Have alternative logic when tasks fail
4. **Document dependencies**: Comment which tasks you're calling and why
5. **Test independently**: Ensure child tasks work before composing them

## Anti-Patterns to Avoid

❌ **Don't return task_run directly:**
```cy
output = task_run("task", {})  # Returns execution object, not task output
```

✅ **Do extract the output:**
```cy
$result = task_run("task", {})
output = $result["output"]
```

❌ **Don't ignore errors:**
```cy
$result = task_run("task", {})
output = $result["output"]  # Will be null if task failed
```

✅ **Do check status:**
```cy
$result = task_run("task", {})
if ($result["status"] == "succeeded") {
    output = $result["output"]
} else {
    return {"error": $result["error"]}
}
```
