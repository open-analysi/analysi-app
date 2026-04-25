# Alert Normalizer

Converts Splunk Notable alerts to the OCSF Detection Finding v1.8.0 format (class 2004).

Each normalizer produces a dict matching the OCSF schema with: `finding_info`, `observables`, `evidences`, `actor`, `device`, `metadata`, `severity_id`, `disposition_id`, etc.

## Critical Fields

### rule_name → finding_info.analytic.name
- **Purpose**: Identifies the detection rule that triggered the alert
- **Workflow matching**: Alerts with the same `rule_name` follow the same investigation workflow
- **Source**: Splunk `rule_name` or `search_name` field
- **OCSF location**: `finding_info.analytic.name` (type_id=1, Rule)
- **Example**: `Possible SQL Injection Payload Detected`

### title vs analytic.name
- `finding_info.title` — human-readable alert summary (may vary per instance)
- `finding_info.analytic.name` — stable detection rule name (used for routing)
- These are different. Never confuse them.

## Design Decisions

### URL Handling
- **Full URLs** (`https://...`) → stored in `evidences[].url.url_string`
- **Paths only** (`/api/users`) → stored in `evidences[].url.path`
- **Always extract path**: Even when we have a full URL, extract and populate path from it

### IOC → Observable Mapping
- IOCs become `observables[]` with OCSF `type_id` values (2=IP, 1=Hostname, 6=URL, 8=Hash, etc.)
- **Internal IPs are NOT observables**: Private IPs (172.16.x.x, 10.x.x.x, 192.168.x.x) go to `device` or `evidences[].src_endpoint`, not `observables`
- **Confidence**: Mapped to `reputation.score_id` (1=Low, 2=Medium, 3=High)

### Network Info → Evidences
- `src_ip`, `dest_ip`, ports → `evidences[].src_endpoint`, `evidences[].dst_endpoint`
- Protocol → `evidences[].connection_info.protocol_name`

### action → disposition_id
- `allowed` → 1 (Allowed), `blocked` → 2 (Blocked), `quarantined` → 3, `detected` → 15

### source_category → metadata.labels
- OCSF has no dedicated source_category field
- Stored as `metadata.labels: ["source_category:Firewall"]`

## Test Data
Test fixtures are in `tests/alert_normalizer/notables/` - 9 demo scenarios covering various attack types.
