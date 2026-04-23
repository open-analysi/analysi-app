# Detection Finding Attributes Reference

Source: [OCSF v1.8.0 Detection Finding](https://schema.ocsf.io/1.8.0/classes/detection_finding)

## Table of Contents
- [Classification Attributes](#classification-attributes)
- [Primary Attributes](#primary-attributes)
- [Context Attributes](#context-attributes)
- [Occurrence Attributes](#occurrence-attributes)
- [Activity Enum](#activity-enum)
- [type_uid Calculation](#type_uid-calculation)
- [Severity Enum](#severity-enum)
- [Status Enum](#status-enum)
- [Confidence Enum](#confidence-enum)
- [Impact Enum](#impact-enum)
- [Risk Level Enum](#risk-level-enum)
- [Validation Checklist](#validation-checklist)

---

## Classification Attributes

| Attribute | Type | Req | Description |
|-----------|------|-----|-------------|
| `activity_id` | Integer | **Required** | Normalized activity — see [Activity Enum](#activity-enum) |
| `activity_name` | String | Optional | Human-readable activity label |
| `category_uid` | Integer | **Required** | Always `2` (Findings) |
| `category_name` | String | Optional | Always `"Findings"` |
| `class_uid` | Integer | **Required** | Always `2004` |
| `class_name` | String | Optional | Always `"Detection Finding"` |
| `severity_id` | Integer | **Required** | See [Severity Enum](#severity-enum) |
| `severity` | String | Optional | Severity caption (e.g., `"High"`) |
| `type_uid` | Long | **Required** | `class_uid × 100 + activity_id` (200400–200499) |
| `type_name` | String | Optional | E.g., `"Detection Finding: Create"` |

## Primary Attributes

| Attribute | Type | Req | Description |
|-----------|------|-----|-------------|
| `finding_info` | Finding Info Object | **Required** | Core detection details — see `finding-info.md` |
| `metadata` | Metadata Object | **Required** | Product/source info — see `metadata-profiles.md` |
| `evidences` | Evidence Artifacts[] | Recommended | Triggering evidence — see `observables-evidence.md` |
| `is_alert` | Boolean | Recommended | `true` if this is an alertable signal |
| `message` | String | Recommended | Source-provided event/finding description |
| `observables` | Observable[] | Recommended | Extracted IOCs — see `observables-evidence.md` |
| `resources` | Resource Details[] | Recommended | Affected resource targets (cloud resources, hosts, etc.) |
| `status_code` | String | Recommended | Source event status code |
| `status_detail` | String | Recommended | Additional outcome information |

## Context Attributes

| Attribute | Type | Req | Description |
|-----------|------|-----|-------------|
| `confidence_id` | Integer | Recommended | See [Confidence Enum](#confidence-enum) |
| `confidence` | String | Optional | Confidence caption |
| `confidence_score` | Integer | Optional | Source-reported confidence (vendor-defined scale) |
| `status_id` | Integer | Recommended | See [Status Enum](#status-enum) |
| `status` | String | Optional | Status caption |
| `impact_id` | Integer | Optional | See [Impact Enum](#impact-enum) |
| `impact` | String | Optional | Impact caption |
| `impact_score` | Integer | Optional | 0–100 scale |
| `risk_level_id` | Integer | Optional | See [Risk Level Enum](#risk-level-enum) |
| `risk_level` | String | Optional | Risk level caption |
| `risk_score` | Integer | Optional | Source-reported risk score |
| `risk_details` | String | Optional | Risk description text |
| `comment` | String | Optional | User-provided annotation |
| `device` | Device Object | Optional | Affected host — key fields: `uid`, `hostname`, `ip`, `type_id`, `os` |
| `enrichments` | Enrichment[] | Optional | External data source augmentation |
| `malware` | Malware[] | Optional | Malware details (name, classification, path, provider, uid) |
| `malware_scan_info` | Malware Scan Info | Optional | Scan job details |
| `remediation` | Remediation Object | Optional | Recommended fix steps (`desc`, `kb_article_list`, `references`) |
| `vulnerabilities` | Vulnerability Details[] | Optional | CVE/vulnerability data |
| `anomaly_analyses` | Anomaly Analysis[] | Optional | Baseline and deviation data |
| `raw_data` | String | Optional | Original event payload |
| `raw_data_hash` | Fingerprint Object | Optional | Hash of `raw_data` for integrity |
| `raw_data_size` | Long | Optional | Byte size of `raw_data` |
| `unmapped` | Object | Optional | Source attributes with no OCSF mapping |
| `vendor_attributes` | Vendor Attributes | Optional | Vendor-populated mutable field values |

## Occurrence Attributes

| Attribute | Type | Req | Description |
|-----------|------|-----|-------------|
| `time` | Timestamp | **Required** | Normalized event occurrence or creation time (epoch ms or RFC 3339) |
| `start_time` | Timestamp | Optional | Earliest event in a correlated finding |
| `end_time` | Timestamp | Optional | Most recent event in a correlated finding |
| `duration` | Long | Optional | Span in milliseconds |
| `count` | Integer | Optional | Event occurrence frequency |
| `timezone_offset` | Integer | Recommended | UTC offset in minutes (−1080 to +1080) |

---

## Activity Enum

`activity_id` → `activity_name`

| ID | Label | type_uid |
|----|-------|----------|
| 0 | Unknown | 200400 |
| 1 | Create | 200401 |
| 2 | Update | 200402 |
| 3 | Close | 200403 |
| 99 | Other | 200499 |

## type_uid Calculation

```
type_uid = class_uid × 100 + activity_id
```

| type_uid | Meaning |
|----------|---------|
| 200400 | Detection Finding: Unknown |
| 200401 | Detection Finding: Create |
| 200402 | Detection Finding: Update |
| 200403 | Detection Finding: Close |
| 200499 | Detection Finding: Other |

## Severity Enum

`severity_id` → `severity`

| ID | Label | Guidance |
|----|-------|---------|
| 0 | Unknown | Severity not determined |
| 1 | Informational | No threat; audit/telemetry |
| 2 | Low | Minimal risk, routine investigation |
| 3 | Medium | Moderate risk, timely review needed |
| 4 | High | Significant threat, prompt response required |
| 5 | Critical | Severe impact, immediate action required |
| 6 | Fatal | System/service failure imminent or occurred |
| 99 | Other | Vendor-specific; check `severity` string |

## Status Enum

`status_id` → `status`

| ID | Label | Lifecycle stage |
|----|-------|----------------|
| 0 | Unknown | Status not set |
| 1 | New | Just created, unreviewed |
| 2 | In Progress | Under active investigation |
| 3 | Suppressed | Intentionally muted (tuning, known-benign) |
| 4 | Resolved | Investigation complete, addressed |
| 5 | Archived | Retained for compliance, no longer active |
| 6 | Deleted | Removed (may appear in audit trail only) |
| 99 | Other | Vendor-specific; check `status` string |

## Confidence Enum

`confidence_id` → `confidence`

| ID | Label |
|----|-------|
| 0 | Unknown |
| 1 | Low |
| 2 | Medium |
| 3 | High |
| 99 | Other |

## Impact Enum

`impact_id` → `impact`

| ID | Label |
|----|-------|
| 0 | Unknown |
| 1 | Low |
| 2 | Medium |
| 3 | High |
| 4 | Critical |
| 99 | Other |

## Risk Level Enum

`risk_level_id` → `risk_level`

| ID | Label |
|----|-------|
| 0 | Info |
| 1 | Low |
| 2 | Medium |
| 3 | High |
| 4 | Critical |
| 99 | Other |

---

## Validation Checklist

When validating a Detection Finding event, verify:

1. `class_uid` equals `2004`
2. `category_uid` equals `2`
3. `type_uid` equals `class_uid × 100 + activity_id`
4. `activity_id` is one of: 0, 1, 2, 3, 99
5. `severity_id` is one of: 0, 1, 2, 3, 4, 5, 6, 99
6. `time` is a valid timestamp (epoch ms or RFC 3339)
7. `finding_info` is present and contains at minimum `uid`
8. `metadata` is present with required `product` and `version`
9. If `status_id` is present, it is one of: 0, 1, 2, 3, 4, 5, 6, 99
10. If `confidence_id` is present, it is one of: 0, 1, 2, 3, 99
11. If `impact_id` is present, it is one of: 0, 1, 2, 3, 4, 99
12. String siblings (`severity`, `status`, `confidence`, etc.) match their `_id` counterparts
