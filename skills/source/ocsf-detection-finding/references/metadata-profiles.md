# Metadata Object and Profiles

Source: [OCSF v1.8.0 Metadata](https://schema.ocsf.io/1.8.0/objects/metadata)

## Table of Contents
- [Metadata Object](#metadata-object)
- [Product Object](#product-object)
- [Applicable Profiles](#applicable-profiles)
- [Security Control Profile](#security-control-profile)
- [Cloud Profile](#cloud-profile)
- [Profile Selection Logic](#profile-selection-logic)

---

## Metadata Object

Required on every Detection Finding. Identifies the reporting product and OCSF schema version.

### Required Fields

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `product` | Product Object | **Required** | Product that reported the event |
| `version` | String | **Required** | OCSF schema version (SemVer, e.g., `"1.8.0"`) |

### Recommended Fields

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `log_name` | String | Recommended | Consumer-facing log name (e.g., S3 bucket, SIEM index) |
| `original_time` | String | Recommended | Original event time string from source |
| `reporter` | Reporter Object | Recommended | Entity that first reported the event |
| `tenant_uid` | String | Recommended | Unique tenant identifier for multi-tenant environments |

### Optional Fields

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `uid` | String | Optional | Unique OCSF event identifier |
| `correlation_uid` | String | Optional | Links related OCSF events across systems |
| `event_code` | String | Optional | Product's native event code |
| `labels` | String[] | Optional | User-defined classification tags |
| `log_provider` | String | Optional | Logging service (e.g., `"AWS CloudWatch"`, `"Splunk"`) |
| `log_format` | String | Optional | Data format origin |
| `log_level` | String | Optional | Event logging level |
| `log_source` | String | Optional | System component origin |
| `log_version` | String | Optional | Original event schema version |
| `logged_time` | Timestamp | Optional | When logging system collected the event |
| `processed_time` | Timestamp | Optional | ETL/pipeline processing timestamp |
| `profiles` | String[] | Optional | Applied profile names (e.g., `["cloud", "security_control"]`) |
| `sequence` | Integer | Optional | Event ordering number |

### Metadata Example

```json
{
  "metadata": {
    "product": {
      "name": "GuardDuty",
      "vendor_name": "AWS",
      "version": "2.0"
    },
    "version": "1.8.0",
    "uid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "log_name": "security-findings",
    "original_time": "2026-04-26T14:30:00Z",
    "tenant_uid": "123456789012",
    "profiles": ["cloud", "security_control"]
  }
}
```

---

## Product Object

Nested inside `metadata.product`. Identifies the reporting security product.

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `name` | String | Recommended | Product name (e.g., `"GuardDuty"`) |
| `vendor_name` | String | Recommended | Vendor (e.g., `"AWS"`) |
| `version` | String | Optional | Product version |
| `uid` | String | Optional | Unique product identifier |
| `feature` | Feature Object | Optional | Specific feature/module |
| `lang` | String | Optional | Language code |
| `url_string` | URL String | Optional | Product URL |

---

## Applicable Profiles

Profiles extend the Detection Finding schema with domain-specific attributes. Apply them via `metadata.profiles` and include the corresponding attributes.

| Profile | Apply When | Adds |
|---------|-----------|------|
| **Cloud** | Finding from cloud provider (AWS, Azure, GCP) | `cloud` object with account, region, provider, project |
| **Container** | Detection involves containers/pods | `container` object with image, name, runtime, orchestrator |
| **Data Classification** | Finding involves classified data | `data_classification` with sensitivity labels, categories |
| **Date/Time** | Enhanced time tracking needed | Additional timezone and calendar attributes |
| **Host** | Endpoint/host-based detection | `host` device object with OS, hostname, agent info |
| **Incident** | Finding feeds incident workflow | `incident_uid`, `incident_type_id`, workflow attributes |
| **Linux Users** | Linux-specific user context | Linux user/group details (uid, gid, shell) |
| **macOS Users** | macOS-specific user context | macOS user details |
| **OSINT** | Open-source intelligence enrichment | Threat intel source, indicators, feed metadata |
| **Security Control** | Producer is a security control | `action_id`, `disposition_id`, `policy` — what the control did |

---

## Security Control Profile

When the producer is a security control (firewall, IPS, EDR, WAF), this profile adds:

| Attribute | Type | Description |
|-----------|------|-------------|
| `action` | String | Label for `action_id` |
| `action_id` | Integer | 0=Unknown, 1=Allowed, 2=Denied, 99=Other |
| `disposition` | String | Label for `disposition_id` |
| `disposition_id` | Integer | 0=Unknown, 1=Allowed, 2=Blocked, 3=Quarantined, 4=Isolated, 5=Deleted, 6=Dropped, 7=Custom Action, 8=Approved, 9=Restored, 10=Exonerated, 99=Other |
| `policy` | Policy Object | Applied policy (name, uid, desc, group) |

---

## Cloud Profile

| Attribute | Type | Description |
|-----------|------|-------------|
| `cloud.provider` | String | `"AWS"`, `"Azure"`, `"GCP"`, etc. |
| `cloud.account.uid` | String | Cloud account ID |
| `cloud.region` | String | Deployment region |
| `cloud.zone` | String | Availability zone |
| `cloud.project_uid` | String | Project/subscription ID |

---

## Profile Selection Logic

```
Is the source a security control (firewall, IPS, EDR, WAF)?
  → Apply "security_control" profile

Is the finding from a cloud provider?
  → Apply "cloud" profile

Does the finding involve containers or Kubernetes?
  → Apply "container" profile

Does the finding involve endpoint/host data?
  → Apply "host" profile

Does the finding trigger or relate to an incident?
  → Apply "incident" profile
```

Multiple profiles can be applied simultaneously. A cloud-based EDR finding might use `["cloud", "host", "security_control"]`.
