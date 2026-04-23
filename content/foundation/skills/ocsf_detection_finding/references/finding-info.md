# Finding Information Object Reference

Source: [OCSF v1.8.0 Finding Info](https://schema.ocsf.io/1.8.0/objects/finding_info)

The `finding_info` object is the **required** core of every Detection Finding. It carries the detection rule metadata, temporal markers, ATT&CK mappings, and data source lineage.

## Table of Contents
- [Fields](#fields)
- [Analytic Object](#analytic-object)
- [Related Analytics](#related-analytics)
- [Product Object (within finding_info)](#product-object)
- [Related Events](#related-events)
- [Mapping Common Rule Formats](#mapping-common-rule-formats)

---

## Fields

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `uid` | String | **Required** | Unique finding identifier (vendor's alert/detection ID) |
| `title` | String | Recommended | Brief summary (e.g., `"Suspicious PowerShell Download Cradle"`) |
| `desc` | String | Optional | Detailed finding description |
| `types` | String[] | Optional | Finding category tags (e.g., `["Malware", "Lateral Movement"]`) |
| `analytic` | Analytic Object | Recommended | The detection rule/logic that fired — see below |
| `related_analytics` | Analytic[] | Optional | Other analytics connected to this finding |
| `attacks` | Attack[] | Optional | MITRE ATT&CK mappings — see `attack-mappings.md` |
| `kill_chain` | Kill Chain Phase[] | Optional | Cyber Kill Chain phases — see `attack-mappings.md` |
| `data_sources` | String[] | Optional | Log sources that fed the detection (e.g., `["Windows Security", "Sysmon"]`) |
| `related_events` | Related Event[] | Optional | Connected events/findings identified by the product |
| `related_events_count` | Integer | Optional | Count of related events |
| `product` | Product Object | Optional | Reporting security product (if different from `metadata.product`) |
| `src_url` | URL String | Optional | Link to finding in source console |
| `tags` | Key-Value[] | Optional | Metadata pairs (e.g., `[{"name": "env", "value": "prod"}]`) |
| `traits` | Trait[] | Optional | Key characteristics extracted from the finding |
| `uid_alt` | String | Optional | Alternative identifier (e.g., vendor's secondary ID) |
| `attack_graph` | Graph | Optional | Attacker pathway visualization |
| `created_time` | Timestamp | Optional | When the finding was first generated |
| `modified_time` | Timestamp | Optional | When the finding record was last updated |
| `first_seen_time` | Timestamp | Optional | Earliest observation of the underlying activity |
| `last_seen_time` | Timestamp | Optional | Most recent observation |

**Applicable profiles:** Data Classification, Date/Time

---

## Analytic Object

The `analytic` describes the detection logic that generated the finding.

**Constraint:** At least one of `name` or `uid` must be present.

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `type_id` | Integer | **Required** | Analytic technique — see enum below |
| `name` | String | Recommended* | Rule/detection name (e.g., `"EICAR Test File Detected"`) |
| `uid` | String | Recommended* | Rule ID (e.g., `"SIG-4523"`, Sigma UUID) |
| `type` | String | Optional | Type caption |
| `category` | String | Optional | Analytic grouping (e.g., `"Endpoint"`, `"Network"`) |
| `desc` | String | Optional | Rule description |
| `version` | String | Optional | Rule version (e.g., `"3.2"`) |
| `algorithm` | String | Optional | Underlying algorithm name |
| `state_id` | Integer | Optional | Operational state — see enum below |
| `state` | String | Optional | State caption |
| `related_analytics` | Analytic[] | Optional | **Deprecated v1.0.0** — use `finding_info.related_analytics` instead |

### Analytic `type_id` Enum

| ID | Label | Use for |
|----|-------|---------|
| 0 | Unknown | Type not determined |
| 1 | Rule | Signature/correlation rules (SIEM, IDS, Sigma, YARA, Suricata) |
| 2 | Behavioral | Behavioral analytics (UEBA, EDR behavioral) |
| 3 | Statistical | Statistical anomaly detection (threshold, baseline deviation) |
| 4 | Learning | ML/DL model inference |
| 5 | Fingerprinting | JA3/JA4, TLS fingerprinting, device fingerprinting |
| 6 | Tagging | Tag-based classification |
| 7 | Keyword Match | Keyword/dictionary matching (DLP) |
| 8 | Regular Expressions | Regex pattern matching |
| 9 | Exact Data Match | Exact data matching (DLP) |
| 10 | Partial Data Match | Partial/fuzzy data matching |
| 11 | Indexed Data Match | Index-based matching |
| 99 | Other | Vendor-specific; check `type` string |

### Analytic `state_id` Enum

| ID | Label |
|----|-------|
| 0 | Unknown |
| 1 | Active |
| 2 | Suppressed |
| 3 | Experimental |
| 99 | Other |

---

## Related Analytics

`related_analytics` is an array of Analytic objects (same schema as above). Use it when multiple detection rules contributed to a single finding — for example, a correlation rule that aggregates sub-rules.

```json
"related_analytics": [
  {"name": "Brute Force Attempt", "uid": "R-101", "type_id": 1},
  {"name": "Credential Spray Model", "uid": "ML-42", "type_id": 4}
]
```

---

## Product Object

When `finding_info.product` is populated, it identifies the specific security product that generated the finding (if different from `metadata.product`):

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Product name (e.g., `"GuardDuty"`) |
| `vendor_name` | String | Vendor (e.g., `"AWS"`) |
| `version` | String | Product version |
| `uid` | String | Product unique identifier |
| `feature` | Feature Object | Specific feature/module that fired |
| `url_string` | String | Product URL |

---

## Related Events

Each item in `related_events` links to another event or finding:

| Field | Type | Description |
|-------|------|-------------|
| `uid` | String | Referenced event's unique ID |
| `type` | String | Event type description |
| `type_uid` | Long | OCSF type_uid of the related event |
| `product_uid` | String | Product that generated the related event |
| `observables` | Observable[] | Observables from the related event |

---

## Mapping Common Rule Formats

| Source Format | `type_id` | `name` | `uid` |
|---------------|-----------|--------|-------|
| Sigma rule | 1 (Rule) | Sigma rule title | Sigma rule ID (UUID) |
| YARA rule | 1 (Rule) | YARA rule name | Rule identifier |
| Splunk correlation | 1 (Rule) | Search name | Saved search ID |
| AWS GuardDuty | 2 (Behavioral) | Finding type | Finding type string |
| ML anomaly model | 4 (Learning) | Model name | Model version/ID |
| Suricata SID | 1 (Rule) | Rule msg field | SID number |
