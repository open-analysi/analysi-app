# Parallel API Workflow Example
# Demonstrates: Parallel execution with for-in loops, error handling, data aggregation

# Get list of targets to analyze
targets = input.targets
log("Starting parallel analysis of ${len(targets)} targets")

# Parallel API calls - these run concurrently!
results = []
errors = []

for (target in targets) {
    try {
        # Each API call runs in parallel
        response = app::api::fetch(
            url=target.url,
            timeout=10
        )

        # Process successful response
        processed = {
            "target": target.name,
            "url": target.url,
            "status": "success",
            "data": response,
            "timestamp": app::utils::now()
        }
        results = results + [processed]
        log("Success: ${target.name}")

    } catch (e) {
        # Handle failures gracefully
        error_record = {
            "target": target.name,
            "url": target.url,
            "status": "failed",
            "error": "${e}"
        }
        errors = errors + [error_record]
        log("Failed: ${target.name} - ${e}")
    }
}

# Calculate statistics
total = len(targets)
successful = len(results)
failed = len(errors)
success_rate = (successful * 100) / total

# Build comprehensive report
report = {
    "summary": {
        "total_targets": total,
        "successful": successful,
        "failed": failed,
        "success_rate": success_rate
    },
    "results": results,
    "errors": errors,
    "execution": "parallel"
}

log("Analysis complete: ${successful}/${total} successful")
return report
