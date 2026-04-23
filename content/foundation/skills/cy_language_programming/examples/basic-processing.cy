# Basic Data Processing Example
# Demonstrates: Variables, lists, dictionaries, string interpolation, native functions

# Parse JSON input data
json_text = input.data
users = from_json(json_text)

# Process user data
user_count = len(users)
log("Processing ${user_count} users")

# Extract and transform data
names = []
scores = []
for (user in users) {
    # Convert names to uppercase
    uppercase_name = uppercase(user.name)
    names = names + [uppercase_name]

    # Collect scores
    scores = scores + [user.score]

    log("Processed: ${user.name} (score: ${user.score})")
}

# Calculate statistics
total_score = sum(scores)
average_score = total_score / user_count

# Build result
result = {
    "summary": {
        "total_users": user_count,
        "average_score": average_score,
        "total_score": total_score
    },
    "users": join(names, ", "),
    "details": "Processed ${user_count} users with average score ${average_score}"
}

# Output as formatted JSON
output = to_json(result, 2)
return output
