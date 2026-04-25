# Splunk Performance Monitoring Queries

This guide provides a comprehensive collection of SPL queries for monitoring Splunk infrastructure performance, troubleshooting issues, and analyzing system health across indexers, search heads, forwarders, and other components.

## Table of Contents

- [Data Ingestion Monitoring](#data-ingestion-monitoring)
- [Event Distribution Analysis](#event-distribution-analysis)
- [Indexer Performance](#indexer-performance)
- [Search Head Performance](#search-head-performance)
- [Forwarder Monitoring](#forwarder-monitoring)
- [System Health & Stability](#system-health--stability)
- [Queue Monitoring](#queue-monitoring)
- [Search Performance Analytics](#search-performance-analytics)

---

## Data Ingestion Monitoring

### Daily Ingest Volume (GB)

Monitor the daily data ingestion volume in gigabytes.

```spl
index=_internal source=*license_usage.log* type=Usage
| eval adj=b/1024/1024/1024*60*24/10
```

**Purpose**: Track data volume trends, capacity planning, and license usage.

**Output**: Daily ingestion volume in gigabytes.

---

### Data Sample Size Analysis

Analyze the size characteristics of events being indexed.

```spl
index=main
| eval event_length=len(_raw)
| stats min(event_length), avg(event_length), max(event_length)
```

**Purpose**: Understand event size distribution for performance tuning and storage planning.

**Output**: Minimum, average, and maximum event lengths in bytes.

---

## Event Distribution Analysis

### Event Count Distribution Statistics

Get statistical distribution of events across indexers.

```spl
| tstats count AS total_events where index=main by splunk_server
| stats max(total_events) as MAX, min(total_events) AS MIN, avg(total_events) as AVG, sum(total_events) as Total, count(total_events) as indexer_count, stdev(total_events) as STD_DEV
| eval Min_Max_Diff_%=100*(MAX-MIN)/MIN
| table indexer_count, Total, MAX, MIN, AVG, Min_Max_Diff_%, STD_DEV
```

**Purpose**: Identify imbalances in data distribution across indexers.

**Output**: Statistical summary showing total events, min/max/avg per indexer, standard deviation, and percentage difference.

**Key Metrics**:
- **Min_Max_Diff_%**: High values (>20%) indicate data skew
- **STD_DEV**: Measure of distribution uniformity

---

### Event Count Details by Indexer

View event counts per indexer sorted by volume.

```spl
| tstats count AS total_events where index=main by splunk_server
| sort -total_events
```

**Purpose**: Identify which indexers are handling the most data.

**Output**: List of indexers with event counts in descending order.

---

## Indexer Performance

### CPU Usage by Indexer

Monitor average CPU utilization across indexers over time.

```spl
index=_introspection (host=*idx* OR host=indx*) component=HostWide
| bucket _time span=10s
| eval total_cpu = 'data.cpu_user_pct' + 'data.cpu_system_pct'
| stats avg(total_cpu) as total_cpu by _time, host
```

**Purpose**: Track indexer CPU utilization trends.

**Output**: Time-series data of average CPU percentage by indexer.

**Alert Thresholds**:
- **Warning**: CPU > 70% sustained
- **Critical**: CPU > 90% sustained

---

### CPU Usage by Process (Indexer)

Break down CPU usage by Splunk process type on indexers.

```spl
index=_introspection (host=*idx* OR host=indx*) component=PerProcess
| bucket _time span=10s
| stats sum(data.normalized_pct_cpu) as total_cpu by _time, host, data.process_type
```

**Purpose**: Identify which Splunk processes are consuming the most CPU.

**Output**: CPU usage breakdown by process type (splunkd, splunk-optimize, etc.).

---

### Memory Usage by Indexer

Monitor total memory consumption on indexers.

```spl
index=_introspection (host=*idx* OR host=indx*) component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host
```

**Purpose**: Track memory usage trends to prevent OOM conditions.

**Output**: Total memory usage in MB by indexer over time.

---

### Memory Usage Percentage by Indexer

Monitor memory usage as a percentage of total available memory.

```spl
index=_introspection (host=*idx* OR host=indx*) component=HostWide
| bucket _time span=10s
| eval pct_mem = ('data.mem_used' / 'data.mem') * 100.0
| stats avg(pct_mem) as pct_mem by _time, host
```

**Purpose**: Identify indexers approaching memory limits.

**Output**: Memory utilization percentage by indexer.

**Alert Thresholds**:
- **Warning**: Memory > 80%
- **Critical**: Memory > 90%

---

### Memory Usage by Process (Indexer)

Break down memory consumption by process type on indexers.

```spl
index=_introspection (host=*idx* OR host=indx*) component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host, data.process_type
```

**Purpose**: Identify memory-intensive processes.

**Output**: Memory usage by process type over time.

---

## Search Head Performance

### CPU Usage by Search Head

Monitor CPU utilization across search heads.

```spl
index=_introspection host=*sh* component=HostWide
| bucket _time span=10s
| eval total_cpu = 'data.cpu_user_pct' + 'data.cpu_system_pct'
| stats avg(total_cpu) as total_cpu by _time, host
```

**Purpose**: Track search head CPU utilization.

**Output**: Time-series CPU percentage data per search head.

---

### CPU Usage by Process (Search Head)

Break down CPU usage by process on search heads.

```spl
index=_introspection host=*sh* component=PerProcess
| bucket _time span=10s
| stats sum(data.normalized_pct_cpu) as total_cpu by _time, host, data.process_type
```

**Purpose**: Identify CPU-intensive search head processes.

**Output**: CPU breakdown by process type.

---

### Memory Usage by Search Head

Monitor memory consumption on search heads.

```spl
index=_introspection host=*sh* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host
```

**Purpose**: Track memory usage trends on search heads.

**Output**: Total memory usage in MB per search head.

---

### Memory Usage Percentage by Search Head

Monitor memory as a percentage of available memory.

```spl
index=_introspection host=*sh* component=HostWide
| bucket _time span=10s
| eval pct_mem = ('data.mem_used' / 'data.mem') * 100.0
| stats avg(pct_mem) as pct_mem by _time, host
```

**Purpose**: Prevent OOM conditions on search heads.

**Output**: Memory utilization percentage.

---

### Memory Usage by Process (Search Head)

Break down memory by process type on search heads.

```spl
index=_introspection host=*sh* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host, data.process_type
```

**Purpose**: Identify memory-intensive search processes.

**Output**: Memory usage breakdown by process.

---

## Forwarder Monitoring

### Universal Forwarder CPU Usage

Monitor CPU usage across universal forwarders.

```spl
index=_introspection host=uf* component=HostWide
| bucket _time span=10s
| eval total_cpu = 'data.cpu_user_pct' + 'data.cpu_system_pct'
| stats avg(total_cpu) as total_cpu by _time, host
```

**Purpose**: Ensure forwarders aren't impacting host system performance.

**Output**: CPU percentage per universal forwarder.

**Best Practice**: UF CPU usage should typically be < 5%.

---

### Universal Forwarder CPU by Process

Break down CPU by process on universal forwarders.

```spl
index=_introspection host=uf* component=PerProcess
| bucket _time span=10s
| stats sum(data.normalized_pct_cpu) as total_cpu by _time, host, data.process_type
```

**Purpose**: Identify CPU-intensive forwarder processes.

**Output**: CPU usage by process type.

---

### Universal Forwarder Memory Usage

Monitor memory consumption on universal forwarders.

```spl
index=_introspection host=uf* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host
```

**Purpose**: Track forwarder memory usage.

**Output**: Memory usage in MB per forwarder.

---

### Universal Forwarder Memory Percentage

Monitor memory as a percentage of available memory.

```spl
index=_introspection host=uf* component=HostWide
| bucket _time span=10s
| eval pct_mem = ('data.mem_used' / 'data.mem') * 100.0
| stats avg(pct_mem) as pct_mem by _time, host
```

**Purpose**: Ensure forwarders aren't consuming excessive memory.

**Output**: Memory utilization percentage.

---

### Universal Forwarder Memory by Process

Break down memory usage by process.

```spl
index=_introspection host=uf* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host, data.process_type
```

**Purpose**: Identify memory usage patterns.

**Output**: Memory breakdown by process type.

---

### Heavy Forwarder CPU Usage

Monitor CPU usage across heavy forwarders.

```spl
index=_introspection host=hwf* component=HostWide
| bucket _time span=10s
| eval total_cpu = 'data.cpu_user_pct' + 'data.cpu_system_pct'
| stats avg(total_cpu) as total_cpu by _time, host
```

**Purpose**: Track heavy forwarder CPU utilization.

**Output**: CPU percentage per heavy forwarder.

---

### Heavy Forwarder CPU by Process

Break down CPU usage by process on heavy forwarders.

```spl
index=_introspection host=hwf* component=PerProcess
| bucket _time span=10s
| stats sum(data.normalized_pct_cpu) as total_cpu by _time, host, data.process_type
```

**Purpose**: Identify CPU-intensive processes on HWFs.

**Output**: CPU usage by process type.

---

### Heavy Forwarder Memory Usage

Monitor memory consumption on heavy forwarders.

```spl
index=_introspection host=hwf* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host
```

**Purpose**: Track HWF memory usage trends.

**Output**: Memory usage in MB.

---

### Heavy Forwarder Memory Percentage

Monitor memory as a percentage of available memory.

```spl
index=_introspection host=hwf* component=HostWide
| bucket _time span=10s
| eval pct_mem = ('data.mem_used' / 'data.mem') * 100.0
| stats avg(pct_mem) as pct_mem by _time, host
```

**Purpose**: Monitor HWF memory utilization.

**Output**: Memory utilization percentage.

---

### Heavy Forwarder Memory by Process

Break down memory usage by process.

```spl
index=_introspection host=hwf* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host, data.process_type
```

**Purpose**: Identify memory consumption patterns.

**Output**: Memory breakdown by process type.

---

## Indexer Cluster Manager (IDM) Monitoring

### IDM CPU Usage

Monitor CPU usage on indexer cluster managers.

```spl
index=_introspection host=idm* component=HostWide
| bucket _time span=10s
| eval total_cpu = 'data.cpu_user_pct' + 'data.cpu_system_pct'
| stats avg(total_cpu) as total_cpu by _time, host
```

**Purpose**: Track cluster manager CPU utilization.

**Output**: CPU percentage over time.

---

### IDM CPU by Process

Break down CPU usage by process on cluster managers.

```spl
index=_introspection host=idm* component=PerProcess
| bucket _time span=10s
| stats sum(data.normalized_pct_cpu) as total_cpu by _time, host, data.process_type
```

**Purpose**: Identify CPU-intensive cluster manager processes.

**Output**: CPU usage by process type.

---

### IDM Memory Usage

Monitor memory consumption on cluster managers.

```spl
index=_introspection host=idm* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host
```

**Purpose**: Track IDM memory usage.

**Output**: Memory usage in MB.

---

### IDM Memory Percentage

Monitor memory as a percentage of available memory.

```spl
index=_introspection host=idm* component=HostWide
| bucket _time span=10s
| eval pct_mem = ('data.mem_used' / 'data.mem') * 100.0
| stats avg(pct_mem) as pct_mem by _time, host
```

**Purpose**: Monitor cluster manager memory utilization.

**Output**: Memory utilization percentage.

---

### IDM Memory by Process

Break down memory usage by process.

```spl
index=_introspection host=idm* component=PerProcess
| bucket _time span=10s
| stats sum(data.mem_used) as mem_mb by _time, host, data.process_type
```

**Purpose**: Identify memory consumption patterns.

**Output**: Memory breakdown by process type.

---

## System Health & Stability

### Crashes by Indexer

Monitor crash events on indexers.

```spl
index=_internal (host=*idx* OR host=indx*) AND source=*crash*log*
| stats count by _time, host
```

**Purpose**: Detect indexer stability issues.

**Output**: Crash counts by indexer over time.

**Action**: Investigate any crashes immediately.

---

### Out-of-Memory Events by Indexer

Monitor OOM killer events on indexers.

```spl
index=_internal (host=*idx* OR host=indx*) AND sourcetype=splunkd OR source=*crash*log* "Out of memory: Killed process"
| stats count by _time, host
```

**Purpose**: Detect memory exhaustion events.

**Output**: OOM event counts by indexer.

**Action**: Investigate memory usage and consider increasing resources.

---

### Error Count by Indexer

Cluster similar errors to identify common issues.

```spl
index=_internal (host=*idx* OR host=indx*) log_level=ERROR OR log_level=FATAL
| cluster showcount=t
| table cluster_count _raw
| sort -cluster_count
```

**Purpose**: Identify the most common error patterns.

**Output**: Clustered errors sorted by frequency.

**Best Practice**: Focus on the top 5 error clusters.

---

### Error Count by Component (Indexer)

Break down errors by Splunk component.

```spl
index=_internal (host=*idx* OR host=indx*) log_level=ERROR OR log_level=FATAL
| stats count by _time, host, component
```

**Purpose**: Identify which components are generating errors.

**Output**: Error counts by component over time.

---

### Splunkd Restart Count by Indexer

Monitor Splunkd restart events on indexers.

```spl
index=_internal (host=*idx* OR host=indx*) AND sourcetype=splunkd OR source=*crash*log* "Splunkd starting (build"
| stats count by _time, host
```

**Purpose**: Track unexpected restarts.

**Output**: Restart counts by indexer.

**Action**: Investigate frequent restarts.

---

### Crashes by Search Head

Monitor crash events on search heads.

```spl
index=_internal host=*sh* AND source=*crash*log*
| stats count by _time, host
```

**Purpose**: Detect search head stability issues.

**Output**: Crash counts by search head.

---

### Crashes by Cluster Manager

Monitor crash events on cluster managers.

```spl
index=_internal (host=*c0m1* OR host=*master*) AND source=*crash*log*
| stats count by _time, host
```

**Purpose**: Detect cluster manager stability issues.

**Output**: Crash counts over time.

**Critical**: Cluster manager crashes can impact entire cluster operations.

---

### Out-of-Memory Events by Search Head

Monitor OOM events on search heads.

```spl
index=_internal host=*sh* AND sourcetype=splunkd OR source=*crash*log* "Out of memory: Killed process"
| stats count by _time, host
```

**Purpose**: Detect memory exhaustion on search heads.

**Output**: OOM event counts.

---

### Splunkd Restart Count by Search Head

Monitor Splunkd restarts on search heads.

```spl
index=_internal host=*sh* AND sourcetype=splunkd OR source=*crash*log* "Splunkd starting (build"
| stats count by _time, host
```

**Purpose**: Track search head restarts.

**Output**: Restart counts by search head.

---

### Error Count by Search Head

Cluster similar errors on search heads.

```spl
index=_internal host=*sh* log_level=ERROR OR log_level=FATAL
| cluster showcount=t
| table cluster_count _raw
| sort -cluster_count
```

**Purpose**: Identify common error patterns on search heads.

**Output**: Clustered errors sorted by frequency.

---

### Error Count by Component (Search Head)

Break down errors by component on search heads.

```spl
index=_internal host=*sh* log_level=ERROR OR log_level=FATAL
| stats count by _time, host, component
```

**Purpose**: Identify which search head components are generating errors.

**Output**: Error counts by component.

---

## Queue Monitoring

### Queue Blocking Detection

Identify blocked queues in the indexing pipeline.

```spl
index=_internal group=queue blocked=true
```

**Purpose**: Detect queue blocking issues that impact throughput.

**Output**: All queue blocking events.

**Critical**: Blocked queues indicate backpressure or resource constraints.

---

### Queue Status Monitoring

Monitor queue fill percentage across the indexing pipeline.

```spl
index=_internal group=queue (name=parsingqueue OR name=aggqueue OR name=typingqueue OR name=indexqueue OR name=splunktcpin)
| eval name=case(
    name=="aggqueue","3 - Aggregation Queue",
    name=="indexqueue","5 - Indexing Queue",
    name=="parsingqueue","2 - Parsing Queue",
    name=="typingqueue","4 - Typing Queue",
    name=="splunktcpin", "1 - TCPIn Queue"
  )
| eval ingest_pipe = if(isnotnull(ingest_pipe), ingest_pipe, "none")
| search ingest_pipe=*
| eval max=if(isnotnull(max_size_kb),max_size_kb,max_size)
| eval curr=if(isnotnull(current_size_kb),current_size_kb,current_size)
| eval fill_perc=round((curr/max)*100,2)
| union [
    search index=_internal (host=*idx* OR host=indx*) source=*metrics.log name=ingest thread=rfsoutput
    | eval ingest_pipe = if(isnotnull(ingest_pipe), ingest_pipe, "none")
    | search ingest_pipe=*
    | eval name="6 - RFS Output Queue"
    | eval fill_perc=round(ratio*100,2)
  ]
```

**Purpose**: Monitor queue health and capacity across the indexing pipeline.

**Output**: Fill percentage for each queue type.

**Queue Flow Order**:
1. TCPIn Queue (data reception)
2. Parsing Queue (event parsing)
3. Aggregation Queue (metric aggregation)
4. Typing Queue (sourcetype determination)
5. Indexing Queue (writing to disk)
6. RFS Output Queue (replication)

**Alert Thresholds**:
- **Warning**: Queue fill > 70%
- **Critical**: Queue fill > 90%

**Troubleshooting**:
- High TCPIn: Increase receiving capacity
- High Parsing: Optimize parsing rules
- High Indexing: Check disk I/O and storage

---

## Search Performance Analytics

### Completed Searches per Minute by Type

Track search completion rate broken down by ad-hoc vs scheduled.

```spl
index=_audit host=*sh* info="completed" action=search search_id!='subsearch_*'
| bucket _time span=1m
| eval search_type = if(savedsearch_name="", "adhoc", "scheduled")
| stats count as searches_per_min by _time, search_type
```

**Purpose**: Monitor search load and capacity.

**Output**: Searches per minute by type (adhoc, scheduled).

**Capacity Planning**: Track trends to determine when to scale search heads.

---

### Skipped Searches per Minute

Monitor scheduled searches that are being skipped.

```spl
index=_internal source=*scheduler.log host=*sh*
| bucket _time span=1m
| stats count as searches_per_min by _time, status
| table *
| search status=*skipped*
```

**Purpose**: Identify scheduler congestion.

**Output**: Count of skipped searches over time.

**Action**: Investigate why searches are being skipped:
- Search head capacity issues
- Searches taking too long
- Concurrent search limits reached

---

### Scheduled Search Average Runtime

Track average runtime for successful scheduled searches.

```spl
index=_internal source=*scheduler.log host=*sh*
| bucket _time span=1m
| stats avg(run_time) as avg_run_time by _time, status
| table *
| search status=*success*
```

**Purpose**: Monitor scheduled search performance trends.

**Output**: Average runtime for successful searches.

**Best Practice**: Set alert if average runtime increases significantly.

---

### Ad-Hoc Search Average Runtime

Track average runtime for ad-hoc user searches.

```spl
index=_audit host=*sh* info="completed" action=search search_id!='subsearch_*'
| bucket _time span=1m
| eval search_type = if(savedsearch_name="", "adhoc", "scheduled")
| stats avg(total_run_time) as avg_run_time by _time, search_type
| table *
| search search_type="adhoc"
```

**Purpose**: Monitor user experience with ad-hoc searches.

**Output**: Average runtime for ad-hoc searches.

**User Experience**:
- Good: < 10 seconds
- Acceptable: 10-60 seconds
- Poor: > 60 seconds

---

## Best Practices

### Dashboard Creation
1. Use these queries as base searches in dashboard panels
2. Set appropriate time ranges (typically last 4 hours or 24 hours)
3. Add trend lines using `timechart` for time-series data
4. Set up threshold visualizations for critical metrics

### Alert Configuration
1. Create alerts for critical thresholds (CPU > 90%, Memory > 90%, crashes, OOMs)
2. Use throttling to prevent alert storms
3. Include context in alert messages (which host, what threshold)
4. Route alerts to appropriate teams (infrastructure, Splunk admins, etc.)

### Performance Optimization
1. Use `tstats` for better performance on indexed fields
2. Limit time ranges to necessary windows
3. Use summary indexing for frequently-run expensive queries
4. Schedule resource-intensive queries during off-peak hours

### Monitoring Strategy
1. Create a dedicated monitoring dashboard with key metrics
2. Review daily for trends and anomalies
3. Investigate sudden changes in patterns
4. Baseline normal behavior to identify deviations

### Capacity Planning
1. Track growth trends over time (data volume, search count, CPU, memory)
2. Project when resources will need scaling
3. Monitor for imbalances (data skew, uneven load distribution)
4. Plan upgrades before hitting capacity limits
