# Splunk Common Pitfalls

Common mistakes and best practices when working with Splunk SPL. Each pitfall includes the incorrect approach, the correct approach, and an explanation.

---

## 1. Using match() in Base Search

`match()` is an eval function that only works within eval statements, not in the base search.

```spl
# WRONG - This will fail
index=main src=1.2.3.5 AND match(_raw, "error pattern")
```

```spl
# CORRECT - Use match() within eval
index=main src=1.2.3.5
| where match(_raw, "error pattern")

# OR use regex in search
index=main src=1.2.3.5 "error pattern"
```

**Why**: The base search uses a different syntax than eval expressions. Use `where match()` or include the pattern as a search term.

---

## 2. Leading Wildcards Cause Full Scans

Starting a search term with a wildcard forces Splunk to scan all events.

```spl
# WRONG - Causes full index scan
index=main *error*
```

```spl
# CORRECT - Wildcard at end is efficient
index=main error*

# CORRECT - Specific term is fastest
index=main fatal_error
```

**Why**: Splunk's index is optimized for prefix matching. Leading wildcards bypass the index and scan raw data.

---

## 3. Missing Index Specification

Omitting the index causes Splunk to search all allowed indexes.

```spl
# WRONG - Searches all indexes
sourcetype=access_combined status=404
```

```spl
# CORRECT - Always specify index
index=web sourcetype=access_combined status=404
```

**Why**: Explicit index specification dramatically reduces data scanned. Always start searches with `index=`.

---

## 4. Using search Command Mid-Pipeline

The `search` command mid-pipeline is less efficient than `where`.

```spl
# WRONG - search command mid-pipeline
index=main
| stats count by user
| search count > 100
```

```spl
# CORRECT - Use where for filtering after transformations
index=main
| stats count by user
| where count > 100
```

**Why**: `where` uses eval expressions which are more efficient for post-aggregation filtering. `search` is primarily for the base search.

---

## 5. Stats Before Filtering

Aggregating before filtering processes unnecessary data.

```spl
# WRONG - Stats on all data, then filter
index=main
| stats sum(bytes) as total_bytes by user
| where total_bytes > 1000000
```

```spl
# CORRECT - Filter in base search when possible
index=main sourcetype=web_access user=admin* bytes>0
| stats sum(bytes) as total_bytes by user
| where total_bytes > 1000000
```

**Why**: Add constraints in the base search (index, sourcetype, field values) to reduce data before aggregation. The post-stats `where` is fine for filtering aggregated results.

---

## 6. Wide Time Ranges Without Constraints

Searching large time ranges without specific constraints is slow.

```spl
# WRONG - One week with minimal filtering
index=main earliest=-7d error
```

```spl
# CORRECT - Add more constraints or narrow time
index=main sourcetype=app_logs host=prod-* earliest=-7d error

# OR use a narrower time range
index=main earliest=-1d error
```

**Why**: Time range is a primary filter. Combine with specific indexes, sourcetypes, and search terms.

---

## 7. Using transaction When stats Suffices

`transaction` is expensive; use `stats` when possible.

```spl
# WRONG - transaction for simple aggregation
index=web
| transaction session_id
| stats avg(duration) as avg_session_time
```

```spl
# CORRECT - Use stats with appropriate functions
index=web
| stats range(_time) as duration by session_id
| stats avg(duration) as avg_session_time
```

**Why**: `transaction` reconstructs events and is memory-intensive. `stats` is much faster for most aggregation needs.

---

## 8. Regex in Base Search

Complex regex patterns in the base search are slow.

```spl
# WRONG - Complex regex in base search
index=main | regex _raw="^\\d{4}-\\d{2}-\\d{2}.*ERROR.*connection refused"
```

```spl
# CORRECT - Filter first, then apply regex
index=main ERROR "connection refused"
| regex _raw="^\\d{4}-\\d{2}-\\d{2}"
```

**Why**: Base search should use indexed terms. Apply regex after narrowing results with simple terms.

---

## 9. NOT vs != Confusion

`NOT` and `!=` behave differently with null values.

```spl
# POTENTIALLY WRONG - Excludes events where status is null
index=main status!=200
```

```spl
# CORRECT - Explicitly handle both cases
index=main NOT status=200

# OR if you want to exclude nulls
index=main status!=200 status=*
```

**Why**: `!=` excludes null values. `NOT field=value` includes events where field is null. Choose based on intent.

---

## 10. Confusing dc() and count()

`dc()` counts distinct values; `count()` counts occurrences.

```spl
# WRONG - Counts occurrences, not unique users
index=main | stats count(user) as user_count
```

```spl
# CORRECT - Count unique users
index=main | stats dc(user) as unique_users

# CORRECT - Count all events with user field
index=main | stats count(user) as events_with_user
```

**Why**: Use `dc()` (distinct count) for unique values. Use `count()` for total occurrences.

---

## 11. Using table Instead of fields

`table` is for output formatting; `fields` is for pipeline optimization.

```spl
# WRONG - table early in pipeline
index=main
| table _time user action
| stats count by user
```

```spl
# CORRECT - Use fields to limit data in pipeline
index=main
| fields _time user action
| stats count by user
```

**Why**: `fields` removes data from the pipeline, improving performance. `table` formats output for display.

---

## 12. Missing fillnull for Charts

Charts may have gaps without explicit null handling.

```spl
# WRONG - Missing data appears as gaps
index=main
| timechart count by status
```

```spl
# CORRECT - Fill nulls for complete visualization
index=main
| timechart count by status
| fillnull value=0
```

**Why**: `fillnull` ensures all time buckets have values, creating smoother charts.

---

## 13. earliest/latest vs Time Picker Conflicts

In-line time modifiers override the time picker, causing confusion.

```spl
# CONFUSING - Time picker shows "Last 24 hours" but search uses 7d
index=main earliest=-7d latest=now
| stats count
```

```spl
# CORRECT for ad-hoc searches - Rely on time picker, don't hardcode
index=main
| stats count

# CORRECT for saved searches/alerts - Use explicit time since no picker
index=main earliest=-1h@h latest=now
| stats count by host
```

**Why**: Explicit `earliest`/`latest` override UI time picker selections. For ad-hoc searches, let users control time via the picker. For saved searches and alerts, explicit times are required.

---

## 14. Subsearch Returning Too Many Results

Subsearches have a 10,000 result limit and 60-second timeout by default.

```spl
# WRONG - May hit limits silently
index=main [search index=users status=active | fields user]
```

```spl
# CORRECT - Explicitly limit and format subsearch
index=main [search index=users status=active | fields user | head 10000 | format]

# BETTER - Use join or lookup for large datasets
index=main
| lookup active_users.csv user OUTPUT status
| where status="active"
```

**Why**: Subsearches have limits. For large result sets, use lookups or join commands instead.

---

## 15. Case Sensitivity in Field Names

Splunk field names are case-sensitive.

```spl
# WRONG - Field name mismatch
index=main
| stats count by USER
```

```spl
# CORRECT - Match exact field name case
index=main
| stats count by user

# To check actual field names
index=main | fieldsummary
```

**Why**: `USER`, `User`, and `user` are different fields. Verify field names with `fieldsummary`.

---

## 16. OR Conditions: Readability Over Micro-Optimization

Multiple OR conditions are fine in the base search, but `IN` is more readable.

```spl
# WORKS but verbose
index=main (status=200 OR status=201 OR status=204)
```

```spl
# CLEANER - Use IN for readability
index=main status IN (200, 201, 204)
```

```spl
# WRONG - Using where for base filtering is slower
index=main
| where status IN (200, 201, 204)
```

**Why**: `IN` in the base search is equivalent to OR in performance but more readable. Avoid using `where` for filtering that could be done in the base search—it runs after event retrieval.

---

## 17. Forgetting eventstats vs stats

`stats` removes events; `eventstats` preserves them.

```spl
# WRONG - Loses individual events
index=main
| stats avg(response_time) as avg_rt by host
| where response_time > avg_rt  # response_time no longer exists!
```

```spl
# CORRECT - Use eventstats to add aggregate while keeping events
index=main
| eventstats avg(response_time) as avg_rt by host
| where response_time > avg_rt
```

**Why**: `stats` aggregates and removes event-level data. `eventstats` adds aggregates to each event.

---

## 18. Dedup Without Sort

`dedup` keeps the first occurrence, which depends on event order.

```spl
# WRONG - Undefined which event is kept
index=main
| dedup user
```

```spl
# CORRECT - Sort first to control which event is kept
index=main
| sort -_time
| dedup user

# This keeps the most recent event per user
```

**Why**: Always sort before `dedup` to ensure predictable results.

---

## 19. Expensive eval in Stats

Complex eval inside stats functions is evaluated per event.

```spl
# SLOW - Complex eval in stats
index=main
| stats sum(eval(if(status>=400, bytes, 0))) as error_bytes
```

```spl
# FASTER - Pre-calculate with eval, then aggregate
index=main
| eval error_bytes = if(status>=400, bytes, 0)
| stats sum(error_bytes) as total_error_bytes
```

**Why**: Pre-calculating with `eval` before `stats` is often faster for complex expressions.

---

## 20. Ignoring Search Job Inspector

Not using Job Inspector for performance analysis.

```spl
# WRONG - Guessing at performance issues
```

**CORRECT**: After running a search:
1. Click "Job" → "Inspect Job"
2. Review "Execution costs" section
3. Check "Search job properties" for:
   - `scanCount` - events scanned
   - `resultCount` - events returned
   - `runDuration` - total time
4. Look for high ratio of scanCount to resultCount (indicates poor filtering)

**Why**: Job Inspector reveals exactly where time is spent. Use it to guide optimization.
