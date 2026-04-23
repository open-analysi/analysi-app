# Time Arithmetic Functions

Complete reference for time arithmetic functions in Cy language.

## Overview

Cy provides 8 native functions for working with timestamps and durations:
- **`add_duration()`** - Add time to timestamp
- **`subtract_duration()`** - Subtract time from timestamp
- **`duration_between()`** - Calculate difference between timestamps
- **`parse_duration()`** - Convert duration string to seconds
- **`format_duration()`** - Format seconds to duration string
- **`timestamp_compare()`** - Compare two timestamps
- **`from_epoch()`** - Convert Unix epoch timestamp to ISO 8601
- **`to_epoch()`** - Convert ISO 8601 timestamp to Unix epoch

All timestamps use **ISO 8601 format** (compatible with `now()` function).

## Duration Format

Duration strings support these units:
- `w` - weeks (7 days)
- `d` - days
- `h` - hours
- `m` - minutes
- `s` - seconds

**Examples:**
```cy
# Duration format examples (used as function arguments)
one_hour = "1h"           # 1 hour
thirty_min = "30m"        # 30 minutes
one_day = "1d"            # 1 day
combined = "1h30m"        # 1 hour 30 minutes
two_days = "2d12h"        # 2 days 12 hours
one_week = "1w"           # 1 week
full = "1w2d3h4m5s"       # Combined units
```

---

## add_duration()

Add duration to an ISO 8601 timestamp.

**Signature:** `add_duration(timestamp, duration) -> string`

**Preserves timezone** from the original timestamp.

### Examples

```cy
# Add 1 hour
time = now()
later = add_duration(time, "1h")
# "2025-10-31T14:30:00Z" → "2025-10-31T15:30:00Z"

# Add 1 day
tomorrow = add_duration(now(), "1d")

# Add combined duration
future = add_duration(now(), "1h30m")

# Timezone preserved
pst_time = "2025-10-31T14:00:00-08:00"
pst_later = add_duration(pst_time, "2h")
# Result: "2025-10-31T16:00:00-08:00"
```

### Security Workflow Use Cases

```cy
# Set token expiry (1 hour from creation)
token_created = alert.created_at
token_expires = add_duration(token_created, "1h")

# Calculate SLA deadline
incident_start = incident.timestamp
sla_deadline = add_duration(incident_start, "4h")
```

---

## subtract_duration()

Subtract duration from an ISO 8601 timestamp.

**Signature:** `subtract_duration(timestamp, duration) -> string`

**Preserves timezone** from the original timestamp.

### Examples

```cy
# Subtract 1 hour
time = now()
earlier = subtract_duration(time, "1h")

# Calculate cutoff time (24 hours ago)
cutoff = subtract_duration(now(), "24h")

# Get time window start (15 minutes ago)
window_start = subtract_duration(now(), "15m")
```

### Security Workflow Use Cases

```cy
# Find alerts from last 15 minutes
cutoff_time = subtract_duration(now(), "15m")
recent_alerts = []
for (a in alerts) {
    if (timestamp_compare(a.time, ">", cutoff_time)) {
        recent_alerts = recent_alerts + [a]
    }
}

# Check stale data (older than 7 days)
stale_cutoff = subtract_duration(now(), "7d")
stale_items = []
for (item in data) {
    if (timestamp_compare(item.timestamp, "<", stale_cutoff)) {
        stale_items = stale_items + [item]
    }
}
```

---

## duration_between()

Calculate duration between two ISO 8601 timestamps.

**Signature:** `duration_between(start, end) -> string`

Returns human-readable duration string (e.g., "2h30m", "1d12h").

### Examples

```cy
# Calculate duration
start = "2025-10-31T14:00:00Z"
end = "2025-10-31T16:30:00Z"
duration = duration_between(start, end)
# Result: "2h30m"

# Negative duration (end before start)
duration = duration_between(end, start)
# Result: "-2h30m"

# Calculate alert age
alert_age = duration_between(alert.created_at, now())
```

### Security Workflow Use Cases

```cy
# Calculate incident response time
response_time = duration_between(
    incident.created_at,
    incident.first_response_at
)
log("Response time: ${response_time}")

# Check if alert processing took too long
processing_time = duration_between(alert.received_at, now())
processing_seconds = parse_duration(processing_time)
if (processing_seconds > parse_duration("5m")) {
    log("Alert processing exceeded 5 minutes")
}
```

---

## parse_duration()

Convert duration string to total seconds (as float).

**Signature:** `parse_duration(duration) -> float`

Useful for comparing durations or threshold checking.

### Examples

```cy
# Parse to seconds
seconds = parse_duration("1h")
# Result: 3600.0

seconds = parse_duration("1h30m")
# Result: 5400.0

seconds = parse_duration("1d")
# Result: 86400.0
```

### Security Workflow Use Cases

```cy
# Compare alert age against threshold
alert_age = duration_between(alert.timestamp, now())
age_seconds = parse_duration(alert_age)
threshold_seconds = parse_duration("24h")

if (age_seconds > threshold_seconds) {
    log("Alert is stale (older than 24 hours)")
}

# Check if incident resolution time met SLA
resolution_time = duration_between(incident.opened_at, incident.closed_at)
resolution_seconds = parse_duration(resolution_time)
sla_seconds = parse_duration("4h")

sla_met = resolution_seconds <= sla_seconds
```

---

## format_duration()

Format seconds to human-readable duration string.

**Signature:** `format_duration(seconds) -> string`

Inverse of `parse_duration()`.

### Examples

```cy
# Format seconds to duration
duration = format_duration(3600)
# Result: "1h"

duration = format_duration(5400)
# Result: "1h30m"

duration = format_duration(90061)
# Result: "1d1h1m1s"

# Negative durations
duration = format_duration(-3600)
# Result: "-1h"
```

### Security Workflow Use Cases

```cy
# Calculate and format processing time
start_time = now()
# ... processing happens ...
end_time = now()

processing_seconds = parse_duration(duration_between(start_time, end_time))
formatted = format_duration(processing_seconds)
log("Processing took: ${formatted}")
```

---

## timestamp_compare()

Compare two ISO 8601 timestamps.

**Signature:** `timestamp_compare(timestamp1, operator, timestamp2) -> boolean`

**Operators:** `"<"`, `">"`, `"<="`, `">="`, `"=="`, `"!="`

Handles timezone-aware comparisons correctly.

### Examples

```cy
# Less than
is_before = timestamp_compare(
    "2025-10-31T14:00:00Z",
    "<",
    "2025-10-31T15:00:00Z"
)
# Result: true

# Greater than or equal
is_after = timestamp_compare(
    "2025-10-31T15:00:00Z",
    ">=",
    "2025-10-31T14:00:00Z"
)
# Result: true

# Equality
is_same = timestamp_compare(
    "2025-10-31T14:00:00Z",
    "==",
    "2025-10-31T06:00:00-08:00"  # Same absolute time
)
# Result: true (timezone-aware comparison)
```

### Security Workflow Use Cases

```cy
# Filter recent alerts
cutoff = subtract_duration(now(), "1h")
recent = []
for (a in alerts) {
    if (timestamp_compare(a.time, ">", cutoff)) {
        recent = recent + [a]
    }
}

# Check if SLA deadline passed
sla_deadline = add_duration(incident.created_at, "4h")
sla_breached = timestamp_compare(now(), ">", sla_deadline)

# Find alerts in time range
range_start = "2025-10-31T00:00:00Z"
range_end = "2025-10-31T23:59:59Z"
in_range = []
for (a in alerts) {
    if (timestamp_compare(a.time, ">=", range_start) and timestamp_compare(a.time, "<=", range_end)) {
        in_range = in_range + [a]
    }
}
```

---

## from_epoch()

Convert Unix epoch timestamp (seconds since 1970-01-01 00:00:00 UTC) to ISO 8601 format.

**Signature:** `from_epoch(seconds, timezone?) -> string`

**Parameters:**
- `seconds` - Unix epoch timestamp (float or int)
- `timezone` - Optional timezone name (default: "UTC")

**Common in:** Splunk logs, API responses, database timestamps

### Examples

```cy
# Basic epoch conversion
timestamp = from_epoch(1686839432)
# Result: "2023-06-15T14:30:32Z"

# Unix epoch start
timestamp = from_epoch(0)
# Result: "1970-01-01T00:00:00Z"

# With timezone
timestamp_pst = from_epoch(1686839432, "US/Pacific")
# Result: "2023-06-15T07:30:32-07:00"

# Fractional seconds
timestamp = from_epoch(1686839432.5)
# Result: "2023-06-15T14:30:32.500000Z"

# Negative epoch (before 1970)
timestamp = from_epoch(-86400)
# Result: "1969-12-31T00:00:00Z"
```

### Security Workflow Use Cases

```cy
# Convert Splunk event timestamp
splunk_event_time = event["_time"]  # Epoch format (use bracket notation for _ prefix)
iso_time = from_epoch(splunk_event_time)

# Use in time arithmetic
one_hour_later = add_duration(iso_time, "1h")

# Convert API response timestamp
api_response = {"created_at": 1686839432}
alert_created = from_epoch(api_response.created_at)

# Handle log file timestamps
log_entries = [
    {"message": "Login attempt", "timestamp": 1686839432},
    {"message": "Login success", "timestamp": 1686839492}
]

# Convert to ISO 8601 for processing
events = []
for (entry in log_entries) {
    events = events + [{"message": entry.message, "iso_time": from_epoch(entry.timestamp)}]
}
```

---

## to_epoch()

Convert ISO 8601 timestamp to Unix epoch (seconds since 1970-01-01 00:00:00 UTC).

**Signature:** `to_epoch(timestamp) -> float`

**Returns:** Seconds since Unix epoch as float

**Handles timezone-aware timestamps correctly** - different timezone representations of the same absolute time return the same epoch value.

### Examples

```cy
# Basic conversion
epoch = to_epoch("2023-06-15T14:30:32Z")
# Result: 1686839432.0

# Unix epoch start
epoch = to_epoch("1970-01-01T00:00:00Z")
# Result: 0.0

# Timezone-aware conversion
epoch_utc = to_epoch("2023-06-15T14:30:32Z")
epoch_pst = to_epoch("2023-06-15T07:30:32-07:00")
# Both return: 1686839432.0 (same absolute time)

# Before Unix epoch
epoch = to_epoch("1969-12-31T00:00:00Z")
# Result: -86400.0

# Round trip conversion
original = "2023-06-15T14:30:32Z"
epoch = to_epoch(original)
back_to_iso = from_epoch(epoch)
# back_to_iso == original
```

### Security Workflow Use Cases

```cy
# Send timestamp to API that expects epoch
api_payload = {
    "event_time": to_epoch(alert.triggering_event_time),
    "severity": alert.severity
}

# Calculate seconds since event for threshold checking
event_epoch = to_epoch(event.timestamp)
now_epoch = to_epoch(now())
seconds_since_event = now_epoch - event_epoch

if (seconds_since_event > 3600) {  # 1 hour
    log("Event is more than 1 hour old")
}

# Store in database that uses epoch format
db_record = {
    "id": alert.id,
    "created_at_epoch": to_epoch(alert.created_at),
    "updated_at_epoch": to_epoch(now())
}

# Convert for integration with epoch-based systems
log_entry = {
    "timestamp": to_epoch(now()),
    "level": "INFO",
    "message": "Processing completed"
}
```

---

## Complete Workflow Examples

### Example 1: Alert Age Checking

```cy
# Check if alert is stale (older than 24 hours)
alert_time = alert.triggering_event_time
current_time = now()

# Calculate age
age_duration = duration_between(alert_time, current_time)
age_seconds = parse_duration(age_duration)

# Compare against threshold
threshold_seconds = parse_duration("24h")
is_stale = age_seconds > threshold_seconds

if (is_stale) {
    log("Alert is ${age_duration} old - marking as stale")
    return {"status": "stale", "age": age_duration}
}

return {"status": "active", "age": age_duration}
```

### Example 2: Time Window Filtering

```cy
# Get alerts from last 15 minutes
current_time = now()
window_start = subtract_duration(current_time, "15m")

# Filter alerts
recent_alerts = []
for (a in alerts) {
    if (timestamp_compare(a.timestamp, ">", window_start)) {
        recent_alerts = recent_alerts + [a]
    }
}

log("Found ${len(recent_alerts)} alerts in last 15 minutes")
return recent_alerts
```

### Example 3: SLA Breach Detection

```cy
# Check if incident response exceeded SLA
incident_created = incident.created_at
sla_deadline = add_duration(incident_created, "4h")
current_time = now()

# Check if breached
breached = timestamp_compare(current_time, ">", sla_deadline)

if (breached) {
    # Calculate how much over
    time_over = duration_between(sla_deadline, current_time)
    log("SLA breached by ${time_over}")

    return {
        "sla_status": "breached",
        "deadline": sla_deadline,
        "time_over": time_over
    }
}

# Calculate time remaining
time_remaining = duration_between(current_time, sla_deadline)
return {
    "sla_status": "ok",
    "deadline": sla_deadline,
    "time_remaining": time_remaining
}
```

### Example 4: Session Timeout

```cy
# Check if user session expired
session_created = session.created_at
session_timeout = "1h"
session_expires = add_duration(session_created, session_timeout)

if (timestamp_compare(now(), ">", session_expires)) {
    log("Session expired")
    return {"status": "expired", "expired_at": session_expires}
}

# Calculate time until expiry
time_until_expiry = duration_between(now(), session_expires)
return {
    "status": "active",
    "expires_in": time_until_expiry
}
```

### Example 5: IOC Freshness Check

```cy
# Filter IOCs seen in last 24 hours
freshness_cutoff = subtract_duration(now(), "24h")

fresh_iocs = []
for (ioc in iocs) {
    if (timestamp_compare(ioc.last_seen, ">", freshness_cutoff)) {
        fresh_iocs = fresh_iocs + [ioc]
    }
}

log("Found ${len(fresh_iocs)} fresh IOCs (seen in last 24h)")

# Group by recency
one_hour_ago = subtract_duration(now(), "1h")
very_recent = []
for (ioc in fresh_iocs) {
    if (timestamp_compare(ioc.last_seen, ">", one_hour_ago)) {
        very_recent = very_recent + [ioc]
    }
}

return {
    "fresh_iocs": fresh_iocs,
    "very_recent_iocs": very_recent,
    "freshness_cutoff": freshness_cutoff
}
```

### Example 6: Splunk Log Processing with Epoch Timestamps

```cy
# Process Splunk search results with epoch timestamps
# Splunk returns _time field as Unix epoch
splunk_results = [
    {"_time": 1686839432, "src_ip": "192.168.1.100", "action": "login_attempt"},
    {"_time": 1686839492, "src_ip": "192.168.1.100", "action": "login_success"},
    {"_time": 1686840032, "src_ip": "192.168.1.100", "action": "file_access"}
]

# Convert to ISO 8601 for Cy time arithmetic
events = []
for (result in splunk_results) {
    events = events + [{"timestamp": from_epoch(result["_time"]), "src_ip": result.src_ip, "action": result.action}]
}

# Calculate time between login attempt and success
login_attempt = events[0]
login_success = events[1]

response_time = duration_between(
    login_attempt.timestamp,
    login_success.timestamp
)

log("Login response time: ${response_time}")

# Filter events from last 15 minutes
cutoff = subtract_duration(now(), "15m")
recent_events = []
for (e in events) {
    if (timestamp_compare(e.timestamp, ">", cutoff)) {
        recent_events = recent_events + [e]
    }
}

# Convert back to epoch for API response
api_response = []
for (e in recent_events) {
    api_response = api_response + [{"timestamp_epoch": to_epoch(e.timestamp), "timestamp_iso": e.timestamp, "src_ip": e.src_ip, "action": e.action}]
}

return {
    "total_events": len(events),
    "recent_events": len(recent_events),
    "login_response_time": response_time,
    "events": api_response
}
```

---

## Duration String Reference

### Single Units

| String | Duration |
|--------|----------|
| `"1s"` | 1 second |
| `"1m"` | 1 minute (60 seconds) |
| `"1h"` | 1 hour (3600 seconds) |
| `"1d"` | 1 day (86400 seconds) |
| `"1w"` | 1 week (604800 seconds) |

### Common Durations

| String | Duration | Use Case |
|--------|----------|----------|
| `"30s"` | 30 seconds | Rate limiting window |
| `"5m"` | 5 minutes | Cache TTL |
| `"15m"` | 15 minutes | Recent activity window |
| `"1h"` | 1 hour | Token expiry |
| `"4h"` | 4 hours | SLA deadline |
| `"24h"` | 24 hours | Stale data threshold |
| `"7d"` | 7 days | Data retention |
| `"1w"` | 1 week | Report period |

### Combined Durations

| String | Duration |
|--------|----------|
| `"1h30m"` | 1 hour 30 minutes |
| `"2d12h"` | 2 days 12 hours |
| `"1w2d"` | 1 week 2 days |
| `"2h45m30s"` | 2 hours 45 minutes 30 seconds |

---

## Timezone Handling

All time arithmetic functions **preserve timezone** information from input timestamps.

### Examples

```cy
# UTC timestamp
utc_time = "2025-10-31T14:00:00Z"
utc_later = add_duration(utc_time, "1h")
# Result: "2025-10-31T15:00:00Z"

# PST timestamp
pst_time = "2025-10-31T06:00:00-08:00"
pst_later = add_duration(pst_time, "1h")
# Result: "2025-10-31T07:00:00-08:00"

# Comparison works across timezones
is_same = timestamp_compare(
    "2025-10-31T14:00:00Z",           # 2pm UTC
    "==",
    "2025-10-31T06:00:00-08:00"       # 6am PST (same absolute time)
)
# Result: true
```

### Daylight Saving Time

Python's datetime automatically handles DST transitions when adding/subtracting durations.

---

## Error Handling

All functions validate inputs and raise `ValueError` with clear messages:

```cy
# Invalid timestamp format
add_duration("not-a-timestamp", "1h")
# Error: Invalid ISO 8601 timestamp: 'not-a-timestamp'

# Invalid duration format
parse_duration("invalid")
# Error: Invalid duration format: 'invalid'. Expected format like '1h', '30m', '1h30m'

# Invalid operator
timestamp_compare(time1, "invalid", time2)
# Error: invalid operator: 'invalid'. Valid operators: !=, <, <=, ==, >, >=

# Wrong types
add_duration(123, "1h")
# Error: timestamp must be string, got int
```

---

## Best Practices

### ✅ Do This

```cy
# Use duration_between + parse_duration for comparisons
age_seconds = parse_duration(duration_between(start, end))
if (age_seconds > parse_duration("1h")) {
    log("Older than 1 hour")
}

# Use timestamp_compare for filtering
recent = []
for (i in items) {
    if (timestamp_compare(i.time, ">", cutoff)) {
        recent = recent + [i]
    }
}

# Preserve timezone when working with timestamps
user_timezone_time = add_duration(timestamp, "1h")  # Timezone preserved
```

### ❌ Avoid This

<!-- cy-test: expect-error -->
```cy
# Don't try to manipulate timestamp strings directly
bad = timestamp + "1h"  # Won't work!

# Don't compare duration strings directly
if (duration1 > duration2) { ... }  # Won't work! Use parse_duration()

# Don't forget to handle timezone
# (Time arithmetic functions handle this automatically)
```

---

## Performance Notes

- All functions are **fast** (microsecond scale for typical operations)
- Duration parsing uses compiled regex (cached by Python)
- Timestamp parsing uses Python's optimized `fromisoformat()`
- No network calls or I/O operations

---

## Quick Reference

| Task | Function | Example |
|------|----------|---------|
| Add time | `add_duration()` | `add_duration(now(), "1h")` |
| Subtract time | `subtract_duration()` | `subtract_duration(now(), "24h")` |
| Calculate age | `duration_between()` | `duration_between(alert.time, now())` |
| Convert to seconds | `parse_duration()` | `parse_duration("1h30m")` → `5400.0` |
| Format seconds | `format_duration()` | `format_duration(3600)` → `"1h"` |
| Compare times | `timestamp_compare()` | `timestamp_compare(t1, ">", t2)` |
| Epoch to ISO 8601 | `from_epoch()` | `from_epoch(1686839432)` → `"2023-06-15T14:30:32Z"` |
| ISO 8601 to epoch | `to_epoch()` | `to_epoch("2023-06-15T14:30:32Z")` → `1686839432.0` |
| Get current time | `now()` | `now()` or `now("US/Pacific")` |
