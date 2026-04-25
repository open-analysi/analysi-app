# tstats Command Tutorial

A comprehensive guide to using the `tstats` command for high-performance statistical queries in Splunk.

## Table of Contents

- [Overview](#overview)
- [Why Use tstats?](#why-use-tstats)
- [Basic Syntax](#basic-syntax)
- [Quick Start Examples](#quick-start-examples)
- [Working with Data Models](#working-with-data-models)
- [Arguments Reference](#arguments-reference)
- [Advanced Techniques](#advanced-techniques)
- [Common Patterns](#common-patterns)
- [Limitations and Gotchas](#limitations-and-gotchas)
- [Performance Optimization](#performance-optimization)
- [Troubleshooting](#troubleshooting)

---

## Overview

The `tstats` command performs statistical queries on **indexed fields** in tsidx files. These indexed fields can be from:
- Regular indexed data (index-time fields)
- Accelerated data models

**Key Advantage**: Because `tstats` searches on index-time fields instead of raw events, it is **significantly faster** than the `stats` command.

---

## Why Use tstats?

### Performance Benefits

| Feature | tstats | stats |
|---------|--------|-------|
| **Data Source** | tsidx files (pre-indexed) | Raw events |
| **Speed** | Very fast (10-100x faster) | Slower |
| **Best For** | Large datasets, dashboards, scheduled searches | Ad-hoc searches, complex eval expressions |
| **Data Models** | Works with accelerated data models | Works with any data |

### When to Use tstats

✅ **Use tstats when**:
- Searching large time ranges (days, weeks, months)
- Building dashboards that need fast load times
- Working with accelerated data models
- Queries only need indexed fields
- Performance is critical

❌ **Don't use tstats when**:
- You need search-time extracted fields
- Complex eval expressions are required in aggregations
- Wildcards needed in BY clauses
- Multiple time ranges in one search

---

## Basic Syntax

### Minimal Syntax

```spl
| tstats <stats-function> [FROM datamodel=<name>] [WHERE <filter>] [BY <field-list>]
```

### Complete Syntax

```spl
| tstats
    [prestats=<bool>]
    [summariesonly=<bool>]
    [local=<bool>]
    [fillnull_value=<string>]
    <stats-func>...
    [FROM datamodel=<data_model_name>.<root_dataset_name>]
    [WHERE <search-query> | <field> IN (<value-list>)]
    [BY <field-list> [span=<timespan>]]
```

---

## Quick Start Examples

### Example 1: Basic Event Count

Count events in an index:

```spl
| tstats count WHERE index=main
```

**Output**: Total count of events in the main index.

---

### Example 2: Count by Field

Count events grouped by sourcetype:

```spl
| tstats count WHERE index=main BY sourcetype
```

**Output**:
| sourcetype | count |
|------------|-------|
| access_combined | 1234567 |
| syslog | 987654 |
| json | 456789 |

---

### Example 3: Count Over Time

Count events per hour:

```spl
| tstats count WHERE index=main BY _time span=1h
```

**Time spans**: `1m` (minute), `1h` (hour), `1d` (day), `1w` (week), `1mon` (month)

---

### Example 4: Multiple Aggregations

Calculate multiple statistics:

```spl
| tstats count, avg(bytes), max(bytes), min(bytes) WHERE index=main BY sourcetype
```

**Output**:
| sourcetype | count | avg(bytes) | max(bytes) | min(bytes) |
|------------|-------|------------|------------|------------|
| access_combined | 1000 | 4567 | 98765 | 234 |

---

## Working with Data Models

### Why Data Models?

Data models provide:
- **Pre-computed summaries** (accelerated data)
- **CIM compliance** (standardized field names)
- **Faster searches** on large datasets
- **Hierarchical datasets** for granular queries

### Basic Data Model Query

```spl
| tstats count FROM datamodel=<DataModelName>.<RootDataset>
```

**Example**: Count authentication events

```spl
| tstats count FROM datamodel=Authentication.Authentication
```

---

###Child Dataset Selection

Select a specific child dataset using `nodename`:

```spl
| tstats count
FROM datamodel=Authentication.Authentication
WHERE nodename=Authentication.Failed_Authentication
```

**Hierarchy Example**:
```
Authentication (Data Model)
├── Authentication (Root Dataset)
    ├── Successful_Authentication (Child)
    ├── Failed_Authentication (Child)
    └── Default_Authentication (Child)
```

---

### Data Model with Filters

Combine FROM and WHERE clauses:

```spl
| tstats count
FROM datamodel=Authentication.Authentication
WHERE Authentication.action=failure AND Authentication.src_ip=192.168.1.*
BY Authentication.user, Authentication.dest
```

**Note**: Use the full field path when referencing data model fields (e.g., `Authentication.user`).

---

### summariesonly Parameter

Control whether to search only accelerated data or include raw data:

```spl
| tstats summariesonly=true count
FROM datamodel=Authentication.Authentication
```

| summariesonly | Behavior |
|---------------|----------|
| `true` | Only search accelerated summary data (fast, may be incomplete) |
| `false` (default) | Search summaries + raw data outside summary range (slower, complete) |

**Use Case**: Set `summariesonly=true` for dashboards where speed is prioritized over completeness.

---

## Arguments Reference

### Critical Arguments

#### prestats

**Purpose**: Output in prestats format for piping to `chart`, `stats`, or `timechart`

```spl
| tstats prestats=true count BY sourcetype
| stats count BY sourcetype
```

**When to use**: Advanced scenarios where you need to further process tstats results.

---

#### fillnull_value

**Purpose**: Replace null values in BY clause fields

```spl
| tstats count fillnull_value="Unknown" WHERE index=main BY host, sourcetype
```

**Without fillnull_value**: Rows with null values are omitted
**With fillnull_value**: Null values replaced with specified string

---

#### local

**Purpose**: Force tstats to run only on search head (troubleshooting)

```spl
| tstats local=true count WHERE index=main
```

**Use Case**: Debugging acceleration issues on search heads.

---

#### chunk_size

**Purpose**: Control memory usage for high-cardinality fields

```spl
| tstats chunk_size=100000 count BY high_cardinality_field
```

**Default**: 10,000,000
**Lower values**: More responsive, potentially slower
**Higher values**: Faster completion, more memory usage

---

### Performance Arguments

#### allow_old_summaries

**Purpose**: Use old summaries when data model definition changes

```spl
| tstats allow_old_summaries=true count
FROM datamodel=MyDataModel.MyDataset
```

**Default**: `false` (only use current summaries)
**Set to true**: When old summaries are "good enough"

---

## Advanced Techniques

### Technique 1: Time-Based Aggregation

Create time-series data for dashboards:

```spl
| tstats count WHERE index=firewall earliest=-7d
BY _time, action span=1h
| timechart span=1h sum(count) BY action
```

**Use Case**: Firewall activity over the last week, hourly breakdown.

---

### Technique 2: Top N Results

Find top sourcetypes by volume:

```spl
| tstats count WHERE index=main BY sourcetype
| sort -count
| head 10
```

---

### Technique 3: Multiple Data Models

Combine data from multiple data models using `append`:

```spl
| tstats count FROM datamodel=Authentication.Authentication BY Authentication.src
| append [
    | tstats count FROM datamodel=Network_Traffic.All_Traffic BY All_Traffic.src_ip
]
```

---

### Technique 4: PREFIX() for Raw Segments

Aggregate on raw indexed segments (not extracted fields):

```spl
| tstats count BY PREFIX(user=)
```

**Use Case**: When you have indexed key-value pairs like `user=jdoe` in raw events.

---

### Technique 5: Using IN Operator

Filter by multiple values:

```spl
| tstats count WHERE index=main sourcetype IN (access_combined, syslog, json)
```

---

## Common Patterns

### Pattern 1: Security - Failed Authentication Attempts

```spl
| tstats count
FROM datamodel=Authentication.Authentication
WHERE Authentication.action=failure
BY Authentication.user, Authentication.src, Authentication.dest
| sort -count
```

---

### Pattern 2: Network Traffic Analysis

```spl
| tstats sum(All_Traffic.bytes_in) as bytes_in, sum(All_Traffic.bytes_out) as bytes_out
FROM datamodel=Network_Traffic.All_Traffic
BY All_Traffic.src_ip, All_Traffic.dest_ip
| eval total_bytes = bytes_in + bytes_out
| sort -total_bytes
| head 20
```

---

### Pattern 3: Error Rate Over Time

```spl
| tstats count
FROM datamodel=Web.Web
WHERE Web.status>=400
BY _time span=5m
| timechart span=5m sum(count) as errors
```

---

### Pattern 4: User Activity Baseline

```spl
| tstats count AS activity_count
FROM datamodel=Authentication.Authentication
BY Authentication.user, _time span=1h
| stats avg(activity_count) as baseline_activity, stdev(activity_count) as std_dev BY Authentication.user
```

---

### Pattern 5: Data Ingestion Monitoring

```spl
| tstats count WHERE index=* BY index, host, sourcetype
| stats sum(count) as event_count BY index, sourcetype
| sort -event_count
```

---

## Limitations and Gotchas

### Limitation 1: No Wildcards in BY Clause

❌ **Doesn't work**:
```spl
| tstats count BY source*
```

✅ **Workaround**: Use specific fields or regex post-processing
```spl
| tstats count BY source
| regex source="^/var/log.*"
```

---

### Limitation 2: No Complex Eval in Aggregate Functions

❌ **Doesn't work**:
```spl
| tstats count(eval(status=200))
```

✅ **Workaround**: Use tstats, then eval
```spl
| tstats count BY status
| eval success=if(status=200, count, 0)
| stats sum(success)
```

---

### Limitation 3: No Search-Time Fields

`tstats` only works with **indexed fields**, not fields extracted at search-time.

**Check if field is indexed**:
```spl
| walklex index=main field=myfield
```

---

### Limitation 4: Case-Insensitive WHERE Clause

WHERE clauses are case-insensitive:

```spl
| tstats count WHERE host=MYHOST
```
This matches `myhost`, `MyHost`, `MYHOST`, etc.

---

### Limitation 5: No Multiple Time Ranges

❌ **Doesn't work**:
```spl
| tstats count WHERE (earliest=-5m latest=-4m) OR (earliest=-2m latest=-1m)
```

✅ **Workaround**: Use multiple tstats with append
```spl
| tstats prestats=t count WHERE earliest=-5m latest=-4m
| tstats prestats=t append=true count WHERE earliest=-2m latest=-1m
| stats count
```

---

## Performance Optimization

### Tip 1: Use summariesonly for Dashboards

Sacrifice completeness for speed on dashboards:

```spl
| tstats summariesonly=true count FROM datamodel=Authentication.Authentication
```

**Result**: 10-100x faster, but only searches summarized data.

---

### Tip 2: Limit BY Fields

Fewer BY fields = faster searches:

❌ **Slower**:
```spl
| tstats count BY field1, field2, field3, field4, field5
```

✅ **Faster**:
```spl
| tstats count BY field1, field2
```

---

### Tip 3: Filter Early with WHERE

Push filters into WHERE clause instead of using `search` after tstats:

❌ **Slower**:
```spl
| tstats count BY host
| search host=myhost
```

✅ **Faster**:
```spl
| tstats count WHERE host=myhost BY host
```

---

### Tip 4: Use Data Model Acceleration

Ensure data models are accelerated and up-to-date:

**Check acceleration status**:
```spl
| rest /services/admin/summarization BY datamodel
```

**Enable acceleration**: Settings → Data Models → Edit → Enable Acceleration

---

### Tip 5: Narrow Time Ranges

Limit searches to necessary time windows:

```spl
| tstats count WHERE index=main earliest=-1h latest=now
```

---

## Troubleshooting

### Problem 1: No Results Returned

**Possible Causes**:
1. Data model not accelerated
2. Using search-time fields
3. Data outside summary range with `summariesonly=true`

**Solutions**:
- Check data model acceleration status
- Verify fields are indexed (use `| walklex`)
- Set `summariesonly=false` to include unsummarized data

---

### Problem 2: Results Don't Match stats Command

**Cause**: Different handling of prestats or partial aggregates

**Solution**: Set `use_summary_index_values=true`

```spl
| tstats use_summary_index_values=true count BY sourcetype
```

---

### Problem 3: Too Slow or Using Too Much Memory

**Cause**: High-cardinality fields, large result sets

**Solutions**:
- Lower `chunk_size`
- Reduce BY fields
- Add WHERE filters
- Use shorter time ranges

```spl
| tstats chunk_size=100000 count WHERE index=main earliest=-1h BY high_cardinality_field
```

---

### Problem 4: "WHERE clause is not an exact query" Error

**Cause**: Non-indexed characters or complex expressions in WHERE clause

**Solution**: Simplify WHERE clause or use indexed field-value pairs

---

## Supported Functions

### Aggregate Functions

| Function | Description | Example |
|----------|-------------|---------|
| `count()` | Count events | `count(src_ip)` |
| `avg()` | Average value | `avg(bytes)` |
| `sum()` | Sum values | `sum(bytes_in)` |
| `min()` | Minimum value | `min(response_time)` |
| `max()` | Maximum value | `max(response_time)` |
| `median()` | Median value | `median(latency)` |
| `mode()` | Most common value | `mode(status)` |
| `stdev()` | Standard deviation | `stdev(bytes)` |
| `stdevp()` | Population std dev | `stdevp(bytes)` |
| `var()` | Variance | `var(response_time)` |
| `varp()` | Population variance | `varp(response_time)` |
| `range()` | Max - min | `range(temperature)` |
| `distinct_count()` | Unique count | `distinct_count(user)` |
| `estdc()` | Estimated distinct count | `estdc(user)` |
| `perc<N>()` | Nth percentile | `perc95(response_time)` |
| `exactperc<N>()` | Exact Nth percentile | `exactperc95(latency)` |

### Event Order Functions

| Function | Description | Example |
|----------|-------------|---------|
| `first()` | First value | `first(status)` |
| `last()` | Last value | `last(status)` |

### Time Functions

| Function | Description | Example |
|----------|-------------|---------|
| `earliest()` | Earliest value | `earliest(timestamp)` |
| `earliest_time()` | Earliest _time | `earliest_time(_time)` |
| `latest()` | Latest value | `latest(timestamp)` |
| `latest_time()` | Latest _time | `latest_time(_time)` |
| `rate()` | Events per second | `rate(count)` |

### Multivalue Functions

| Function | Description | Example |
|----------|-------------|---------|
| `values()` | List distinct values | `values(user)` |

---

## Best Practices Summary

1. ✅ **Use tstats for performance-critical searches** (dashboards, scheduled searches)
2. ✅ **Work with accelerated data models** for maximum speed
3. ✅ **Set summariesonly=true** on dashboards when appropriate
4. ✅ **Filter early** using WHERE clause
5. ✅ **Use indexed fields only** - verify with `walklex`
6. ✅ **Limit BY clause fields** to what's necessary
7. ✅ **Narrow time ranges** to required windows
8. ✅ **Monitor data model acceleration** status
9. ❌ **Don't use wildcards** in BY clauses
10. ❌ **Don't use complex eval** in aggregate functions

---

## Quick Reference Card

### Basic Queries

```spl
# Count all events
| tstats count WHERE index=main

# Count by field
| tstats count WHERE index=main BY sourcetype

# Count over time
| tstats count WHERE index=main BY _time span=1h

# Multiple stats
| tstats count, avg(bytes), max(bytes) WHERE index=main BY host
```

### Data Model Queries

```spl
# Basic data model
| tstats count FROM datamodel=Authentication.Authentication

# With filters
| tstats count FROM datamodel=Web.Web WHERE Web.status>=400

# Child dataset
| tstats count FROM datamodel=Auth.Auth WHERE nodename=Auth.Failed

# Summaries only
| tstats summariesonly=true count FROM datamodel=Network.Traffic
```

### Time-Based Queries

```spl
# Hourly aggregation
| tstats count BY _time span=1h

# Daily aggregation
| tstats count BY _time span=1d

# Custom time range
| tstats count WHERE earliest=-7d latest=now
```

---

## Additional Resources

- **Splunk Docs**: Official `tstats` command reference
- **Data Models**: Learn about accelerating data models
- **CIM Add-on**: Common Information Model for standardized field names
- **Performance Tuning**: limits.conf settings for `tstats`
- **Index-Time Fields**: fields.conf configuration

---

**Version**: Based on Splunk Enterprise 9.2 Documentation
