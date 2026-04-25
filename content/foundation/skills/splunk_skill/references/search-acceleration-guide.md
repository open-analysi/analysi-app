# Splunk Search Acceleration Guide

A comprehensive guide to search acceleration techniques in Splunk, including tstats, data models, summary indexing, and report acceleration.

Based on "Searching FAST: How to Start Using tstats and Other Acceleration Techniques" by David Veuve, Principal Security Strategist at Splunk (September 2017).

## Table of Contents

- [Overview](#overview)
- [Why Acceleration Matters](#why-acceleration-matters)
- [Acceleration Techniques Comparison](#acceleration-techniques-comparison)
- [Data Models and TSIDX Architecture](#data-models-and-tsidx-architecture)
- [Transitioning from Raw Searches to tstats](#transitioning-from-raw-searches-to-tstats)
- [Real-World Performance Examples](#real-world-performance-examples)
- [Advanced Topics](#advanced-topics)
- [Limitations and Workarounds](#limitations-and-workarounds)
- [Getting Started](#getting-started)

---

## Overview

Search acceleration techniques allow you to query Splunk data orders of magnitude faster by pre-computing aggregations and leveraging indexed field data. These techniques are essential for:
- Reducing Total Cost of Ownership (TCO)
- Enabling comprehensive data analysis at scale
- Building fast-loading dashboards
- Supporting real-time analytics

**Key Insight**: tstats powers everything Splunk Inc does internally and can provide 10-10,000x speed improvements over traditional searches.

---

## Why Acceleration Matters

### The Cost of Raw Searches

When searching raw data, Splunk must:
1. Access raw event data from disk
2. Decompress the data
3. Run field extractions at search time
4. Re-check filters against extracted fields
5. Perform aggregations

This process is **CPU and disk expensive**, especially for large datasets.

### The Power of TSIDX

Data model queries using tstats:
- Reside entirely within Time Series Index (TSIDX) files
- **Never visit raw logs**
- Use a lexicon structure where fields and values are stored as `field::value` (e.g., `bar::AB`)
- Enable highly efficient indexed field searching

**Result**: Queries that would take hours or days complete in seconds.

---

## Acceleration Techniques Comparison

Splunk provides four main acceleration techniques, each with different use cases:

### 1. Summary Indexing (SI)

**Mechanism**: Stores search results into a new index using the `| collect` command.

**Use Cases**:
- Accelerating results where search-based data models cannot be accelerated
- Pre-computing complex statistics (e.g., login counts)
- Processing email logs or transaction data

**Benefits**:
- No license consumption for summary data
- Can accelerate any search result

**Drawbacks**:
- Lacks multiple levels of time granularity
- Requires manual coordination
- Less flexible than other methods

**Example**:
```spl
index=main sourcetype=access_combined
| stats count by status
| collect index=summary_index
```

---

### 2. Report Acceleration (RA)

**Mechanism**: Takes a single saved search (using `stats`, `timechart`, `top`, or `chart`) and automatically pre-computes aggregates across multiple time buckets (e.g., per 10m, per hour).

**Use Cases**:
- Accelerating frequently-run reports
- Dashboard panels with consistent queries
- Simple statistical aggregations

**Benefits**:
- Super fast and easy to configure
- Auto backfill and recovery
- Multiple time granularities
- Automatically falls back to raw data when needed

**Drawbacks**:
- Limited to a single search per job
- Supports only basic analytics
- No complex transformations

**Configuration**:
Enable in saved search settings: "Accelerate Report"

---

### 3. Accelerated Pivot (AP)

**Mechanism**: Drag-and-drop statistical interface powered by accelerated data models. The Pivot UI actually runs tstats behind the scenes.

**Use Cases**:
- Non-technical users building analytics
- Rapid prototyping of data analysis
- Exploring data model contents

**Benefits**:
- Super easy, no SPL required
- Automatically switches between accelerated data and raw logs
- Visual interface for building queries

**Drawbacks**:
- Pivot search language is "weirder than tstats"
- Not entirely accelerated by default
- Less flexible than direct tstats queries

**Access**: Settings → Data Models → Select Model → Pivot

---

### 4. tstats Command (Recommended)

**Mechanism**: Operates on accelerated data models, `tscollect` files, and index-time field extractions (`source`, `host`, `index`, `sourcetype`).

**Use Cases**:
- High-performance dashboards
- Large-scale data analysis
- Security analytics at scale
- Any statistical query requiring speed

**Benefits**:
- Distributed indexed field searching
- Full flexibility of search language
- "Faster than you've ever imagined life to be"
- `summariesonly=t` prevents fallback to raw data for maximum speed

**Limitations**:
- Can only perform statistical operations
- Cannot search raw logs directly
- Requires accelerated data models or index-time fields

**Example**:
```spl
| tstats summariesonly=t count
FROM datamodel=Network_Traffic.All_Traffic
WHERE All_Traffic.dest_ip=192.168.1.*
BY All_Traffic.src_ip, All_Traffic.dest_port
```

---

## Acceleration Technique Selection Guide

| Criterion | Summary Indexing | Report Acceleration | Accelerated Pivot | tstats |
|-----------|------------------|---------------------|-------------------|--------|
| **Ease of Use** | Moderate | Easy | Very Easy | Moderate |
| **Speed** | Moderate | Fast | Very Fast | Very Fast |
| **Flexibility** | High | Low | Low | High |
| **Best For** | Search-based models | Simple reports | Non-technical users | Power users |
| **Time Granularity** | Manual | Automatic | Automatic | Full control |
| **SPL Required** | Yes | Yes | No | Yes |

**Recommendation**: Start with Accelerated Pivot for exploration, then transition to tstats for production dashboards and scheduled searches.

---

## Data Models and TSIDX Architecture

### What Can Be Accelerated

**Accelerated Data Models** can define anything configurable via `props` and `transforms`:
- Field extractions using regex
- Field aliases
- Calculated fields
- Lookups

**Critical Requirement**: Only **raw events** can be accelerated. Data models based on:
- Searches (e.g., using `search` command)
- Transaction commands
- Complex transformations

Must use Summary Indexing instead.

### TSIDX Lexicon Structure

TSIDX files store data using a lexicon structure:
```
field::value
```

**Example**:
```
host::webserver01
sourcetype::access_combined
status::200
status::404
dest_ip::192.168.1.100
```

This structure enables:
- Rapid field-value lookups
- Efficient filtering without decompression
- Statistical operations without accessing raw events

### Accelerating Slow Extractions

If your data model includes slow field extractions:
```spl
| eval myfield=spath(_raw, "path.to.my.field")
```

Accelerating this field makes queries using it **super fast** with pivot or tstats, since the extraction is pre-computed.

---

## Transitioning from Raw Searches to tstats

### Step-by-Step Process

1. **Build or identify the data model** containing your fields
2. **Identify the aggregation** you want to perform (e.g., `stats count`)
3. **Adjust the syntax** from raw search to tstats

### Syntax Conversion Examples

#### Example 1: Without Data Models

**Raw Search**:
```spl
index=* | stats count by index, sourcetype
```

**tstats Equivalent**:
```spl
| tstats count WHERE index=* BY index, sourcetype
```

**Note**: `BY` replaces `by`, `WHERE` replaces initial search filters.

---

#### Example 2: With Data Models

**Raw Search**:
```spl
tag=network tag=traffic
| stats dc(dest_ip) by src_ip
```

**tstats Equivalent**:
```spl
| tstats dc(All_Traffic.dest_ip)
FROM datamodel=Network_Traffic
BY All_Traffic.src_ip
```

**Note**: Field names must be prefixed with the dataset name (`All_Traffic.dest_ip`).

---

### Identifying Data Model Field Names

Three methods to determine the correct field names:

#### Method 1: Pivot Interface
1. Go to Settings → Data Models
2. Select your data model
3. Click "Pivot"
4. Observe field names in the interface

#### Method 2: datamodelsimple Command (CIM App)
```spl
| datamodelsimple datamodel=Network_Traffic
```

Lists all fields in the data model with their full paths.

#### Method 3: walklex Command
```spl
| walklex index=main type=field
```

Queries TSIDX files directly to show available indexed fields.

---

### tstats Syntax Details

#### WHERE Clause

Works similarly to initial raw search criteria:

**Supported**:
```spl
| tstats count WHERE index=main sourcetype=access_combined status=200
```

**Not Supported**:
- Certain punctuation characters
- `splunk_server_group` (mostly)
- `cidrmatches()` function (wildcards work instead)

#### Grouping by Time

Direct time-based grouping without `bucket` command:

**tstats**:
```spl
| tstats count BY index, _time span=1h
```

**Equivalent Raw**:
```spl
index=* | bucket _time span=1h | stats count by index, _time
```

---

## Real-World Performance Examples

### Example 1: Splunk Internal UBA - Counting Sourcetypes

**Scenario**: Count events by sourcetype across massive dataset

**Raw Search**: 68,476 seconds (19 hours)
**tstats Query**: 6.19 seconds

**Speed Improvement**: **11,062x faster**

---

### Example 2: Financial Customer XML - Dashboard Loading

**Scenario**: Dashboard with heavy XML extraction using spath

**Unaccelerated Pivots**: 172,800 seconds (2 days)
**Accelerated Pivots**: 16 seconds

**Speed Improvement**: **10,000x faster**

---

### Example 3: Complex Security Correlation

**Scenario**: Correlating Sysmon, proxy, and antivirus data

**Raw Search**: 21 seconds
**Multi-datamodel tstats**: 2 seconds

**Speed Improvement**: **10.5x faster**

**Query Example**:
```spl
| tstats summariesonly=t count
FROM datamodel=Endpoint.Processes
BY Processes.process_name, Processes.user
| append [
  | tstats summariesonly=t count
  FROM datamodel=Web.Proxy
  BY Proxy.user, Proxy.url
]
| stats values(*) by user
```

---

## Advanced Topics

### Key Settings: summariesonly and allow_old_summaries

These are the most important settings for tstats performance:

#### summariesonly=t

**Purpose**: Forces the search to only use accelerated data, never falling back to raw events.

**When to use**:
- Dashboards requiring maximum speed
- Scheduled searches with tight time windows
- When you know acceleration is complete

**Trade-off**: May miss recent data if acceleration lags behind real-time.

**Example**:
```spl
| tstats summariesonly=t count FROM datamodel=Authentication.Authentication
```

#### allow_old_summaries=t

**Purpose**: Allows using accelerated summaries even when the data model definition has changed.

**When to use**:
- After updating the Common Information Model (CIM)
- When searching data generated by different app versions
- When data model structure changes but old summaries are "good enough"

**Example**:
```spl
| tstats allow_old_summaries=t count FROM datamodel=Network_Traffic.All_Traffic
```

---

### prestats=t and Multiple Namespaces

#### prestats=t

**Purpose**: Outputs results in a format suitable for piping into upstream `stats` commands.

**Use Cases**:
- Combining tstats with additional statistical processing
- Post-processing aggregated results

**Example**:
```spl
| tstats prestats=t count BY sourcetype
| stats count BY sourcetype
| eval count_millions = count / 1000000
```

#### Multiple Data Models with append

**Pattern**: When searching across multiple data models, use `prestats=t` and `append=t`, followed by `coalesce` to normalize field names.

**Example**:
```spl
| tstats prestats=t count FROM datamodel=Authentication.Authentication
BY Authentication.user, Authentication.dest
| append [
  | tstats prestats=t count FROM datamodel=Network_Traffic.All_Traffic
  BY All_Traffic.user, All_Traffic.dest
]
| stats count BY user, dest
| eval user = coalesce(Authentication.user, All_Traffic.user)
| eval dest = coalesce(Authentication.dest, All_Traffic.dest)
```

---

### Time and _indextime

#### _indextime Field

**Purpose**: Indexed field representing when the event was indexed (vs. `_time` which is when the event occurred).

**Use Cases**:
- Calculating indexing lag
- Monitoring data freshness
- Detecting delayed data

**Supported Operations**:
- Filtering: `WHERE _indextime > relative_time(now(), "-1h")`
- NOT supported: Aggregations like `avg(_indextime)` or `sum(_indextime)`

**Lag Calculation Example**:
```spl
| tstats latest(_time) as event_time, latest(_indextime) as index_time
WHERE index=main BY host
| eval lag_seconds = index_time - event_time
| eval lag_minutes = round(lag_seconds / 60, 2)
| where lag_minutes > 5
```

#### _time Limitations

When querying `_time` with tstats:

**Supported**:
- `min(_time)`
- `max(_time)`
- `BY _time span=...`

**NOT Supported**:
- `avg(_time)`
- `range(_time)`
- `sum(_time)`

---

### Cardinality Management

#### Split-By Cardinality

**Issue**: If the cardinality of split-by fields is extremely high (millions of unique values), tstats must store all rows in memory, causing performance degradation.

**Solution**: Summary index the results daily, then process those summaries using tstats.

**Example**:
```spl
# Daily summary indexing
index=main sourcetype=firewall
| stats count by src_ip, dest_ip, dest_port
| collect index=summary_firewall_daily

# Query summaries with tstats
| tstats sum(count) FROM datamodel=SummaryData
WHERE index=summary_firewall_daily
BY src_ip, dest_ip
```

#### Field Cardinality

**Issue**: High field cardinality (many unique values) results in massive TSIDX file sizes, consuming disk space and slowing searches.

**Solution**: Round off unnecessary precision before acceleration.

**Example**:
If temperature data has 7 decimal places:
```
72.3456789°F
72.3456788°F
72.3456787°F
```

Round it before acceleration:
```spl
| eval temp_rounded = round(temperature, 1)
```

This reduces unique values from millions to hundreds, dramatically reducing TSIDX size.

---

## Limitations and Workarounds

### Limitation 1: Search-Based Data Models

**Issue**: Data models based on searches (using `search` command) or transaction commands cannot be accelerated.

**Workaround**:
1. Use Summary Indexing to store search results
2. Configure index-time field extractions on the summary index
3. Query the summary index with tstats

**Example**:
```spl
# Step 1: Summary index the search
index=main sourcetype=transactions
| transaction user maxspan=30m
| stats count, avg(duration) by user
| collect index=summary_transactions

# Step 2: Configure props.conf for summary index
[source::stash_*/summary_transactions]
EXTRACT-user = user=(?<user>\w+)
EXTRACT-count = count=(?<count>\d+)
EXTRACT-avg_duration = avg_duration=(?<avg_duration>[\d.]+)

# Step 3: Query with tstats
| tstats avg(avg_duration) WHERE index=summary_transactions BY user
```

---

### Limitation 2: Extremely High Cardinality

**Issue**: When split-by fields result in millions of rows, tstats performance suffers due to memory constraints.

**Workaround**: Use cascading summary indexes.

**Pattern**:
1. Daily summary index: Aggregate raw data by hour
2. Weekly summary: Query daily summaries with tstats
3. Monthly summary: Query weekly summaries with tstats

**Example**:
```spl
# Daily: Aggregate raw data
index=main | bucket _time span=1h
| stats count by _time, user, action
| collect index=summary_daily

# Weekly: Aggregate daily summaries with tstats
| tstats sum(count) WHERE index=summary_daily earliest=-7d
BY user, action
| collect index=summary_weekly
```

---

### Limitation 3: Unsupported WHERE Clause Operators

**Issue**: Certain operators and functions don't work in tstats WHERE clauses:
- `cidrmatches()` (use wildcards instead)
- Complex regex patterns
- Some punctuation characters

**Workaround**: Filter after tstats using `search` or `where`.

**Example**:
```spl
| tstats count FROM datamodel=Network_Traffic.All_Traffic
BY All_Traffic.src_ip
| search src_ip="10.0.*" OR src_ip="192.168.*"
```

---

## Getting Started

### Recommended Path

1. **Start with Accelerated Pivot on Data Models**
   - Familiarize yourself with data model structure
   - Experiment with drag-and-drop analytics
   - Observe the tstats queries generated

2. **Use tstats on Normal Indexed Data**
   - Practice with simple queries: `| tstats count WHERE index=*`
   - Check event counts by sourcetype
   - Monitor index time lag

3. **Build Your First Accelerated Data Model**
   - Identify a frequently-searched dataset
   - Create a data model for it
   - Enable acceleration
   - Convert existing searches to tstats

4. **Transition Production Dashboards**
   - Identify slow-loading dashboard panels
   - Convert searches to tstats
   - Use `summariesonly=t` for maximum speed
   - Monitor performance improvements

---

## Quick Reference: Conversion Patterns

### Basic Count
```spl
# Raw
index=main | stats count

# tstats
| tstats count WHERE index=main
```

### Count by Field
```spl
# Raw
index=main | stats count by host

# tstats
| tstats count WHERE index=main BY host
```

### Time-Based Aggregation
```spl
# Raw
index=main | bucket _time span=1h | stats count by _time, sourcetype

# tstats
| tstats count WHERE index=main BY _time span=1h, sourcetype
```

### Data Model Query
```spl
# Raw
tag=authentication action=failure | stats count by user, src

# tstats
| tstats count FROM datamodel=Authentication.Authentication
WHERE Authentication.action=failure
BY Authentication.user, Authentication.src
```

### Multiple Aggregations
```spl
# Raw
index=main | stats count, avg(bytes), max(bytes) by host

# tstats
| tstats count, avg(bytes), max(bytes) WHERE index=main BY host
```

---

## Best Practices Summary

1. ✅ **Enable data model acceleration** for frequently-searched datasets
2. ✅ **Use summariesonly=t** on dashboards for maximum speed
3. ✅ **Set allow_old_summaries=t** when CIM versions change
4. ✅ **Round metric data** before acceleration to reduce TSIDX size
5. ✅ **Use cascading summary indexes** for extremely high cardinality
6. ✅ **Filter early** in WHERE clause rather than after tstats
7. ✅ **Monitor acceleration status** regularly (Settings → Data Models)
8. ✅ **Start simple** with index-time fields before complex data models
9. ❌ **Don't accelerate search-based data models** (use summary indexing)
10. ❌ **Don't ignore cardinality issues** (can cause memory problems)

---

## Performance Expectations

Based on real-world examples, expect:
- **10-100x** speed improvement for typical queries
- **1,000-10,000x** speed improvement for complex dashboards with heavy extractions
- **Sub-second response times** for queries that previously took minutes or hours

**Key Insight**: tstats is not difficult, it just requires a mindset shift from searching raw events to querying indexed fields and pre-computed aggregations.

---

**Reference**: Based on "Searching FAST: How to Start Using tstats and Other Acceleration Techniques" by David Veuve, Splunk Principal Security Strategist, September 2017.
