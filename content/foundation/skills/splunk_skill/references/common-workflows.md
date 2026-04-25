# Splunk Common Workflows

Step-by-step procedures for common Splunk tasks. Each workflow provides a structured approach to achieve specific goals.

---

## Building a Dashboard Query

Transform raw data into optimized dashboard visualizations.

### Steps

1. **Start with the base search**
   - Specify index, sourcetype, and time range
   - Use the most restrictive filters first
   ```spl
   index=web sourcetype=access_combined earliest=-24h
   ```

2. **Filter for relevant events**
   - Apply specific search terms
   - Use `where` for complex conditions
   ```spl
   | where status >= 400
   ```

3. **Extract or calculate needed fields**
   - Use `eval` for calculations
   - Use `rex` for field extraction
   ```spl
   | eval response_class = case(status<300,"2xx",status<400,"3xx",status<500,"4xx",true(),"5xx")
   ```

4. **Aggregate using stats or timechart**
   - Choose appropriate aggregation command
   ```spl
   | timechart span=1h count by response_class
   ```

5. **Format results for visualization**
   - Rename fields for readability
   - Apply formatting functions
   ```spl
   | rename response_class as "Response Class"
   ```

6. **Optimize for dashboard performance**
   - Consider using `tstats` for accelerated data models
   - Use summary indexing for expensive calculations
   - Implement post-processing for multiple panels sharing base data

---

## Troubleshooting Performance Issues

Diagnose and resolve slow Splunk searches.

### Steps

1. **Identify slow queries using Job Inspector**
   - Open Job Inspector from search results
   - Review execution phases: dispatch, parsing, running
   - Check "Search job properties" for run time breakdown

2. **Check time range scope**
   - Verify time range isn't unnecessarily wide
   - Use `earliest` and `latest` explicitly
   - Consider time-based index partitioning

3. **Review search command order**
   - Ensure filtering commands appear early
   - Move `eval` and transforming commands after filters
   - Check for unnecessary wildcards at start of terms

4. **Move filters earlier in the pipeline**
   ```spl
   # Before (slow)
   index=main | stats count by user | where count > 100

   # After (faster)
   index=main user=* | stats count by user | where count > 100
   ```

5. **Consider acceleration options**
   - Report acceleration for repeated searches
   - Data model acceleration for tstats queries
   - Summary indexing for expensive aggregations

6. **Reference optimization tips**
   - Avoid leading wildcards (`*error` is slow)
   - Use `fields` command to limit returned data
   - Replace `transaction` with `stats` where possible

---

## Creating Field Extractions

Extract structured fields from unstructured log data.

### Steps

1. **Examine raw event data**
   - Run base search without transformations
   - Identify consistent patterns in `_raw`
   ```spl
   index=main sourcetype=custom_app | head 100
   ```

2. **Identify the pattern to extract**
   - Look for delimiters (spaces, commas, equals signs)
   - Note field positions and formats
   - Example pattern: `user=john action=login status=success`

3. **Build regex with named groups**
   - Use `(?P<fieldname>pattern)` syntax
   - Test with simple patterns first
   ```regex
   user=(?P<user>\w+)\s+action=(?P<action>\w+)\s+status=(?P<status>\w+)
   ```

4. **Test extraction using rex command**
   ```spl
   index=main sourcetype=custom_app
   | rex field=_raw "user=(?P<user>\w+)\s+action=(?P<action>\w+)"
   | table _time user action
   ```

5. **Validate extracted fields**
   - Check for null values (extraction failures)
   - Verify against known data
   ```spl
   | stats count by user action | where isnull(user)
   ```

6. **Consider making extraction permanent**
   - Add to `props.conf` and `transforms.conf`
   - Use Field Extractor UI for guided creation
   - Test in dev before deploying to production

---

## Security Investigation Workflow

Investigate security incidents using Splunk data.

### Steps

1. **Define investigation scope**
   - Identify IOCs (IPs, domains, hashes, usernames)
   - Determine relevant time window
   - List data sources to query

2. **Search for IOC presence**
   ```spl
   index=* (src_ip="10.0.0.50" OR dest_ip="10.0.0.50" OR user="suspicious_user")
   earliest=-7d
   | stats count by index sourcetype
   ```

3. **Build timeline of activity**
   ```spl
   index=* src_ip="10.0.0.50" earliest=-7d
   | table _time index sourcetype action src_ip dest_ip user
   | sort _time
   ```

4. **Correlate across data sources**
   ```spl
   index=firewall OR index=proxy OR index=endpoint src_ip="10.0.0.50"
   | eval data_source=index
   | timechart count by data_source
   ```

5. **Identify related entities**
   ```spl
   index=* src_ip="10.0.0.50" earliest=-7d
   | stats values(dest_ip) as dest_ips, values(user) as users, dc(dest_ip) as unique_dests
   ```

6. **Document findings**
   - Export key searches as reports
   - Note timeline of events
   - Capture evidence with `outputlookup` or dashboard

---

## Log Analysis Workflow

Analyze application logs to identify patterns and issues.

### Steps

1. **Understand log structure**
   ```spl
   index=app_logs sourcetype=myapp | head 20
   | rex field=_raw "(?P<log_level>\w+)\s+\[(?P<thread>[^\]]+)\]\s+(?P<class>[^\s]+)\s+-\s+(?P<message>.*)"
   ```

2. **Identify error patterns**
   ```spl
   index=app_logs log_level=ERROR
   | stats count by message
   | sort -count
   | head 20
   ```

3. **Analyze error frequency over time**
   ```spl
   index=app_logs log_level=ERROR
   | timechart span=1h count by class
   ```

4. **Find error correlations**
   ```spl
   index=app_logs log_level=ERROR
   | transaction thread maxspan=5m
   | table _time thread eventcount message
   ```

5. **Compare against baseline**
   ```spl
   index=app_logs log_level=ERROR earliest=-7d
   | timechart span=1d count
   | eventstats avg(count) as avg_errors
   | eval deviation = count - avg_errors
   ```

6. **Create monitoring alert**
   - Save search with threshold condition
   - Configure alert action (email, webhook)
   - Set appropriate throttling

---

## Alert Creation Workflow

Build effective Splunk alerts for monitoring and incident response.

### Steps

1. **Define alert criteria**
   - What condition should trigger the alert?
   - What is the acceptable threshold?
   - What time window should be monitored?

2. **Build the base search**
   ```spl
   index=security sourcetype=auth action=failure
   | stats count by user
   | where count > 5
   ```

3. **Test and tune threshold**
   - Run against historical data
   - Adjust threshold to minimize false positives
   - Consider time-of-day patterns

4. **Configure scheduling**
   - Set appropriate run frequency
   - Align with data latency (real-time vs scheduled)
   - Consider cron notation for specific times

5. **Set up alert actions**
   - Email notification with relevant fields
   - Webhook to ticketing system
   - Custom script for automated response

6. **Implement throttling**
   - Suppress duplicate alerts within window
   - Group by key field (e.g., per-user throttling)
   ```
   Throttle: Suppress alerts triggered on user for 1 hour
   ```

7. **Document and review**
   - Add description explaining alert purpose
   - Schedule periodic review of alert effectiveness
   - Track false positive rate

---

## Data Onboarding Workflow

Bring new data sources into Splunk effectively.

### Steps

1. **Understand the data**
   - Collect sample log files
   - Identify format (JSON, CSV, syslog, custom)
   - Note timestamp formats and line breaking patterns

2. **Choose ingestion method**
   - Universal Forwarder for server logs
   - HTTP Event Collector (HEC) for applications
   - Scripted inputs for APIs
   - DB Connect for databases

3. **Configure source type**
   - Create custom sourcetype in `props.conf`
   - Set timestamp extraction
   - Configure line breaking
   ```ini
   [custom_app_logs]
   TIME_FORMAT = %Y-%m-%d %H:%M:%S
   LINE_BREAKER = ([\r\n]+)
   SHOULD_LINEMERGE = false
   ```

4. **Create field extractions**
   - Define in `transforms.conf` for reuse
   - Test extractions against sample data
   - Consider CIM compliance for security data

5. **Set up index**
   - Create dedicated index if appropriate
   - Configure retention policy
   - Set appropriate access controls

6. **Validate ingestion**
   ```spl
   index=new_index sourcetype=custom_app earliest=-1h
   | stats count by host source
   ```

7. **Document and train**
   - Document sourcetype and field meanings
   - Create example searches
   - Train users on querying new data
