# Observables & Evidence Artifacts Reference

Source: [OCSF v1.8.0 Observable](https://schema.ocsf.io/1.8.0/objects/observable) | [Evidence Artifacts](https://schema.ocsf.io/1.8.0/objects/evidences)

## Table of Contents
- [Observable Object](#observable-object)
- [Observable type_id Enum](#observable-type_id-enum)
- [Reputation Object](#reputation-object)
- [Evidence Artifacts Object](#evidence-artifacts-object)
- [Evidence verdict_id Enum](#evidence-verdict_id-enum)

---

## Observable Object

Observables are IOCs and key data points extracted from a detection. Each observable ties a named attribute to its value and type.

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `type_id` | Integer | **Required** | Value type — see [enum below](#observable-type_id-enum) |
| `name` | String | Recommended | Attribute reference path (e.g., `"src_endpoint.ip"`, `"file.name"`) |
| `value` | String | Optional | The observable value (e.g., `"192.168.1.100"`, `"evil.exe"`) |
| `type` | String | Optional | Type caption |
| `reputation` | Reputation Object | Optional | Threat reputation data — see [below](#reputation-object) |
| `event_uid` | String | Optional | `metadata.uid` of the source OCSF event |
| `type_uid` | Long | Optional | `type_uid` of the source OCSF event |

The `name` field should use dot-notation pointing to the OCSF attribute path where the value originates.

### Usage Pattern

```json
"observables": [
  {"name": "src_endpoint.ip", "type_id": 2, "value": "10.0.0.55"},
  {"name": "file.hashes[0]", "type_id": 8, "value": "d41d8cd98f00b204e9800998ecf8427e"},
  {"name": "dst_endpoint.domain", "type_id": 1, "value": "c2.malicious.example"}
]
```

---

## Observable type_id Enum

### Dictionary Types (simple string values)

| ID | Type | Example value |
|----|------|---------------|
| 0 | Unknown | — |
| 1 | Hostname | `"web-server-01"` |
| 2 | IP Address | `"192.168.1.100"` or `"2001:db8::1"` |
| 3 | MAC Address | `"00:1A:2B:3C:4D:5E"` |
| 4 | User Name | `"jdoe"` |
| 5 | Email Address | `"user@example.com"` |
| 6 | URL String | `"https://evil.example/payload"` |
| 7 | File Name | `"malware.exe"` |
| 8 | Hash | `"d41d8cd98f00b204e9800998ecf8427e"` |
| 9 | Process Name | `"powershell.exe"` |
| 10 | Resource UID | `"arn:aws:ec2:us-east-1:123:instance/i-abc"` |
| 11 | Port | `"443"` |
| 12 | Subnet | `"10.0.0.0/24"` |

### Dictionary Attributes (contextual strings)

| ID | Type | Example value |
|----|------|---------------|
| 13 | Command Line | `"cmd.exe /c whoami"` |
| 14 | Country | `"US"` (ISO 3166-1 Alpha-2) |
| 15 | Process ID | `"4832"` |
| 16 | HTTP User-Agent | `"Mozilla/5.0 ..."` |
| 19 | User Credential ID | credential identifier |

### Object-Specific Attributes (reference a sub-field of an OCSF object)

| ID | Type | Points to |
|----|------|-----------|
| 17 | CWE uid | `cwe.uid` |
| 18 | CVE uid | `cve.uid` |
| 31 | User uid | `user.uid` |
| 32 | Group name | `group.name` |
| 33 | Group uid | `group.uid` |
| 34 | Account name | `account.name` |
| 35 | Account uid | `account.uid` |
| 36 | Script Content | script body text |
| 37 | Serial Number | device/certificate serial |
| 38 | Resource Details name | `resource.name` |
| 39 | Process Entity uid | `process_entity.uid` |
| 40 | Email subject | `email.subject` |
| 41 | Email uid | `email.uid` |
| 42 | Message UID | message identifier |
| 43 | Registry Value name | `reg_value.name` |
| 44 | Advisory uid | `advisory.uid` |
| 45 | File Path | `"/var/log/auth.log"` |
| 46 | Registry Key Path | `"HKLM\\Software\\..."` |
| 47 | Device uid | `device.uid` |
| 48 | Network Endpoint uid | `network_endpoint.uid` |

### Object Types (represent full OCSF objects)

| ID | Type |
|----|------|
| 20 | Endpoint (Device) |
| 21 | User |
| 22 | Email |
| 23 | Uniform Resource Locator |
| 24 | File |
| 25 | Process |
| 26 | Geo Location |
| 27 | Container |
| 28 | Registry Key |
| 29 | Registry Value |
| 30 | Fingerprint |

| 99 | Other | Vendor-specific; check `type` string |

---

## Reputation Object

Attached to observables when threat intelligence enrichment is available.

| Field | Type | Description |
|-------|------|-------------|
| `score_id` | Integer | Normalized score: 0=Unknown, 1=Very Safe, 2=Safe, 3=Probably Safe, 4=Leans Safe, 5=May not be Safe, 6=Exercise Caution, 7=Suspicious/Risky, 8=Possibly Malicious, 9=Probably Malicious, 10=Malicious, 99=Other |
| `score` | String | Score caption |
| `base_score` | Float | Source-reported raw score |
| `provider` | String | TI provider name (e.g., `"VirusTotal"`, `"AbuseIPDB"`) |

---

## Evidence Artifacts Object

Evidence artifacts link concrete triggering data to the detection. Each item in the `evidences` array can contain multiple evidence types simultaneously.

**Constraint:** At least one substantive attribute must be present (any of the starred fields below).

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `actor` | Actor Object | Recommended* | User/role/process that sourced the activity |
| `api` | API Details | Recommended* | API call that triggered detection |
| `connection_info` | Network Connection Info | Recommended* | Network connection details |
| `container` | Container Object | Recommended | Container context |
| `data` | JSON | Optional* | Unstructured additional evidence (use sparingly) |
| `database` | Database Object | Recommended* | Database involved in detection |
| `databucket` | Databucket Object | Recommended* | Storage bucket involved |
| `device` | Device Object | Recommended* | Host/device associated with trigger |
| `dst_endpoint` | Network Endpoint | Recommended* | Destination endpoint |
| `email` | Email Object | Recommended* | Email associated with detection |
| `file` | File Object | Recommended* | File associated with trigger |
| `http_request` | HTTP Request | Recommended | HTTP request details |
| `http_response` | HTTP Response | Recommended | HTTP response details |
| `ja4_fingerprint_list` | JA4+ Fingerprint[] | Recommended | TLS fingerprints |
| `job` | Job Object | Recommended* | Scheduled job involved |
| `name` | String | Optional | Evidence type name |
| `process` | Process Object | Recommended* | Process associated with trigger |
| `query` | DNS Query Object | Recommended* | DNS query involved |
| `reg_key` | Registry Key Object | Recommended* | Windows registry key |
| `reg_value` | Registry Value Object | Recommended* | Windows registry value |
| `resources` | Resource Details[] | Recommended | Cloud resources |
| `script` | Script Object | Recommended* | Script content |
| `src_endpoint` | Network Endpoint | Recommended* | Source endpoint |
| `tls` | TLS Object | Recommended | TLS session details |
| `uid` | String | Optional | Evidence unique identifier |
| `url` | URL Object | Recommended* | URL involved |
| `user` | User Object | Recommended* | Target/associated user |
| `verdict_id` | Integer | Optional | See [verdict enum](#evidence-verdict_id-enum) |
| `verdict` | String | Optional | Verdict caption |
| `win_service` | Windows Service | Recommended* | Windows service involved |

### Evidence Example — Process-Based Detection

```json
{
  "evidences": [
    {
      "process": {
        "pid": 4832,
        "name": "powershell.exe",
        "cmd_line": "powershell -enc SQBFAFgAIAAoAE4AZQB3AC...",
        "file": {
          "name": "powershell.exe",
          "path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        },
        "user": {
          "name": "jdoe",
          "uid": "S-1-5-21-123456-1001"
        }
      },
      "actor": {
        "user": {
          "name": "jdoe",
          "type_id": 1
        }
      },
      "verdict_id": 2,
      "verdict": "True Positive"
    }
  ]
}
```

### Evidence Example — Network Detection

```json
{
  "evidences": [
    {
      "src_endpoint": {
        "ip": "10.1.2.50",
        "port": 49152
      },
      "dst_endpoint": {
        "ip": "203.0.113.50",
        "port": 443,
        "domain": "c2.evil.example.com"
      },
      "connection_info": {
        "protocol_name": "TCP",
        "direction_id": 2
      },
      "query": {
        "hostname": "c2.evil.example.com",
        "type": "A"
      }
    }
  ]
}
```

---

## Evidence verdict_id Enum

`verdict_id` on an evidence artifact indicates investigation outcome:

| ID | Label |
|----|-------|
| 0 | Unknown |
| 1 | False Positive |
| 2 | True Positive |
| 3 | Disregard |
| 4 | Suspicious |
| 5 | Benign |
| 6 | Test |
| 7 | Insufficient Data |
| 8 | Security Risk |
| 9 | Managed Externally |
| 10 | Duplicate |
| 99 | Other |
