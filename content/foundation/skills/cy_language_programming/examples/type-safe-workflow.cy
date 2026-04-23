# Type-Safe Workflow Example
# Demonstrates: Type-checked tool calls, input validation, type inference

# NOTE: Run with type checking enabled:
# cy = Cy(check_types=True, tools={...})
# Input schema is auto-derived from input_data when check_types=True

# Input validation - types checked against schema
user_id = input.user_id           # Type: string (from schema)
risk_threshold = input.threshold   # Type: number (from schema)
enable_blocking = input.auto_block # Type: boolean (from schema)

log("Starting type-safe analysis for user ${user_id}")

# Type-checked tool call with named arguments
# Tool signature: fetch_user_data(user_id: str) -> dict
user_data = app::users::fetch_user_data(user_id=user_id)

# Type-checked arithmetic operations
activity_score = user_data.login_count * 2
failed_attempts = user_data.failed_logins
risk_score = activity_score + (failed_attempts * 10)

log("Calculated risk score: ${risk_score}")

# Type-safe conditional logic
status = "normal"
if (risk_score > risk_threshold) {
    status = "suspicious"
}

# Type-checked tool calls with multiple arguments
# Tool signature: analyze_behavior(user_id: str, score: int, detailed: bool) -> dict
behavior_analysis = app::security::analyze_behavior(
    user_id=user_id,
    score=risk_score,
    detailed=True
)

# Type inference - confidence is inferred as number
confidence = behavior_analysis.confidence_score

# Type-safe list operations
alerts = []
if (status == "suspicious") {
    alert = {
        "user_id": user_id,
        "risk_score": risk_score,
        "confidence": confidence,
        "timestamp": app::utils::now()
    }
    alerts = alerts + [alert]
}

# Conditional action based on type-checked boolean
action_taken = "none"
if (enable_blocking and risk_score > 90) {
    # Type-checked tool call
    # Tool signature: block_user(user_id: str, reason: str) -> dict
    block_result = app::security::block_user(
        user_id=user_id,
        reason="High risk score detected"
    )
    action_taken = "blocked"
    log("User ${user_id} blocked automatically")
}

# Build type-safe output structure
result = {
    "user_id": user_id,
    "analysis": {
        "risk_score": risk_score,
        "status": status,
        "confidence": confidence,
        "threshold_exceeded": risk_score > risk_threshold
    },
    "behavior": behavior_analysis,
    "alerts": alerts,
    "action_taken": action_taken,
    "summary": "User ${user_id} assessed as ${status} with risk score ${risk_score}"
}

return result

# Type checking benefits demonstrated:
# 1. Input fields validated against schema
# 2. Tool calls validated against signatures
# 3. Arithmetic operations type-checked (number + number)
# 4. String operations validated
# 5. Conditional expressions type-safe
# 6. Return type inferred and validated
