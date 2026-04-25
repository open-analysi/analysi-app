# Splunk Metrics for Observability

This reference covers Splunk's metrics functionality for observability and performance monitoring use cases. **Most security workflows use event data, not metrics.** Only load this reference when explicitly working with time-series metric data (e.g., infrastructure monitoring, APM, cloud metrics).

---

## When to Use Metrics

Metrics are appropriate for:
- Infrastructure monitoring (CPU, memory, disk, network)
- Application performance monitoring (APM)
- Cloud resource utilization (AWS CloudWatch, Azure Monitor, GCP metrics)
- Custom application metrics (counters, gauges, histograms)
- High-volume numeric time-series data

**Not for**: Security logs, authentication events, firewall logs, endpoint detection—use standard event searches for these.

---

## Metrics Concepts

### What Are Metrics?
Time-series numeric data consisting of:
- **Timestamp**: When the measurement was taken
- **Metric name**: Identifier (e.g., `cpu.percent`, `memory.used`)
- **Numeric value**: The measurement
- **Dimensions**: Optional metadata (host, region, service)

### Metrics vs Events
| Aspect | Metrics | Events |
|--------|---------|--------|
| Data type | Numeric time-series | Structured/unstructured logs |
| Storage | Optimized metric store | Standard indexes |
| Query commands | `mstats`, `mcatalog`, `mpreview` | `search`, `stats`, `tstats` |
| Use case | Monitoring, alerting on thresholds | Investigation, correlation |

---

## Metrics Commands

### mstats
Aggregate metrics data. Similar to `stats` but optimized for metric indexes.

```spl
| mstats avg(_value) WHERE metric_name="cpu.percent" by host span=5m
```

**Common aggregations**:
```spl
| mstats avg(_value), max(_value), min(_value), count(_value)
  WHERE metric_name="memory.used"
  by host
  span=1h
```

**Multiple metrics**:
```spl
| mstats avg(_value) as avg_value
  WHERE metric_name IN ("cpu.percent", "memory.percent")
  by metric_name, host
  span=10m
```

### mcatalog
List available metrics and dimensions in metric indexes.

```spl
| mcatalog values(metric_name) WHERE index=metrics
```

**List dimensions for a metric**:
```spl
| mcatalog values(host), values(region) WHERE metric_name="cpu.percent"
```

**Count metrics by dimension**:
```spl
| mcatalog values(metric_name) as metrics WHERE index=metrics by host
| stats count(metrics) by host
```

### mpreview
Preview metric data before it's fully indexed. Useful for validating ingestion.

```spl
| mpreview index=metrics target_per_timeseries=5
```

---

## Common Metrics Queries

### Infrastructure Monitoring

**CPU usage by host**:
```spl
| mstats avg(_value) as cpu_avg, max(_value) as cpu_max
  WHERE metric_name="cpu.percent" index=metrics
  by host
  span=5m
```

**Memory utilization trend**:
```spl
| mstats avg(_value) as memory_percent
  WHERE metric_name="memory.used_percent" index=metrics
  by host
  span=1h
| timechart avg(memory_percent) by host
```

**Disk space alerts**:
```spl
| mstats latest(_value) as disk_used_percent
  WHERE metric_name="disk.used_percent" index=metrics
  by host, mount
| where disk_used_percent > 80
```

### Cloud Metrics (AWS Example)

**EC2 CPU utilization**:
```spl
| mstats avg(_value)
  WHERE metric_name="aws.ec2.CPUUtilization" index=aws_metrics
  by InstanceId
  span=5m
```

**Lambda invocations**:
```spl
| mstats sum(_value) as invocations
  WHERE metric_name="aws.lambda.Invocations" index=aws_metrics
  by FunctionName
  span=1h
```

### Application Metrics

**Request latency percentiles**:
```spl
| mstats perc50(_value) as p50, perc95(_value) as p95, perc99(_value) as p99
  WHERE metric_name="http.request.duration" index=app_metrics
  by service
  span=5m
```

**Error rate**:
```spl
| mstats sum(_value) as errors
  WHERE metric_name="http.errors" index=app_metrics
  by service, status_code
  span=1h
| where errors > 0
```

---

## Metrics Ingestion

### HTTP Event Collector (HEC) for Metrics
Send metrics via HEC with the `event` field containing metric data:

```json
{
  "time": 1609459200,
  "event": "metric",
  "source": "app_metrics",
  "host": "webserver01",
  "fields": {
    "metric_name": "cpu.percent",
    "_value": 45.2,
    "region": "us-west-2"
  }
}
```

### Metrics Index Configuration
Create a dedicated metrics index in `indexes.conf`:

```ini
[metrics]
datatype = metric
homePath = $SPLUNK_DB/metrics/db
coldPath = $SPLUNK_DB/metrics/colddb
thawedPath = $SPLUNK_DB/metrics/thaweddb
```

---

## Best Practices

1. **Use dedicated metric indexes**: Separate metrics from events for optimal storage and query performance
2. **Choose appropriate span**: Match aggregation span to data resolution and use case
3. **Limit dimensions**: High-cardinality dimensions increase storage and slow queries
4. **Use mcatalog first**: Discover available metrics before writing queries
5. **Aggregate at ingest**: Pre-aggregate high-volume metrics when possible
