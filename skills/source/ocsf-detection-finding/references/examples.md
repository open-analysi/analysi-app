# Detection Finding JSON Examples

Complete, valid examples for common scenarios. All examples target OCSF v1.8.0.

## Table of Contents
- [Minimal Valid Event](#minimal-valid-event)
- [Full Create Event (EDR Alert)](#full-create-event-edr-alert)
- [Cloud Detection (AWS GuardDuty)](#cloud-detection-aws-guardduty)
- [Update Event (Status Change)](#update-event-status-change)
- [Close Event](#close-event)
- [Common Mapping Patterns](#common-mapping-patterns)

---

## Minimal Valid Event

The absolute minimum to produce a schema-valid Detection Finding. Only required fields are populated.

```json
{
  "activity_id": 1,
  "category_uid": 2,
  "class_uid": 2004,
  "severity_id": 3,
  "type_uid": 200401,
  "time": 1711670400000,
  "metadata": {
    "product": {
      "name": "Example SIEM",
      "vendor_name": "ExampleCorp"
    },
    "version": "1.8.0"
  },
  "finding_info": {
    "uid": "FIND-0001"
  }
}
```

**Validation notes:** `type_uid` = 2004 × 100 + 1 = 200401. `finding_info.uid` is the only strictly required nested field. `metadata.product` and `metadata.version` are both required. `time` can be epoch milliseconds (integer) or RFC 3339 string.

---

## Full Create Event (EDR Alert)

A realistic EDR detection with observables, evidence, ATT&CK mapping, and Kill Chain phase.

```json
{
  "activity_id": 1,
  "activity_name": "Create",
  "category_uid": 2,
  "category_name": "Findings",
  "class_uid": 2004,
  "class_name": "Detection Finding",
  "type_uid": 200401,
  "type_name": "Detection Finding: Create",
  "severity_id": 4,
  "severity": "High",
  "time": 1711670400000,
  "timezone_offset": -300,
  "confidence_id": 3,
  "confidence": "High",
  "status_id": 1,
  "status": "New",
  "is_alert": true,
  "message": "Suspicious PowerShell download cradle detected on WORKSTATION-42",
  "metadata": {
    "product": {
      "name": "Endpoint Protector",
      "vendor_name": "SecVendor",
      "version": "5.2.1",
      "uid": "ep-prod-001"
    },
    "version": "1.8.0",
    "uid": "evt-a1b2c3d4",
    "log_name": "edr-alerts",
    "tenant_uid": "tenant-xyz-123",
    "profiles": ["Host", "Security Control"]
  },
  "finding_info": {
    "uid": "DET-2024-0042",
    "title": "PowerShell Download Cradle",
    "desc": "PowerShell process executed encoded download command targeting known malicious domain",
    "types": ["Malware", "Command and Control"],
    "analytic": {
      "name": "Encoded PowerShell Download Detection",
      "uid": "SIG-PS-1042",
      "type_id": 1,
      "type": "Rule",
      "category": "Endpoint",
      "version": "3.1"
    },
    "attacks": [
      {
        "tactic": {"uid": "TA0002", "name": "Execution"},
        "technique": {"uid": "T1059", "name": "Command and Scripting Interpreter"},
        "sub_technique": {"uid": "T1059.001", "name": "PowerShell"},
        "version": "v14"
      },
      {
        "tactic": {"uid": "TA0011", "name": "Command and Control"},
        "technique": {"uid": "T1105", "name": "Ingress Tool Transfer"},
        "version": "v14"
      }
    ],
    "kill_chain": [
      {"phase_id": 4, "phase": "Exploitation"},
      {"phase_id": 6, "phase": "Command & Control"}
    ],
    "data_sources": ["Microsoft-Windows-Sysmon/Operational", "Microsoft-Windows-PowerShell/Operational"],
    "src_url": "https://console.secvendor.example/alerts/DET-2024-0042",
    "created_time": 1711670400000,
    "first_seen_time": 1711670380000,
    "last_seen_time": 1711670400000
  },
  "observables": [
    {"name": "device.hostname", "type_id": 1, "value": "WORKSTATION-42"},
    {"name": "src_endpoint.ip", "type_id": 2, "value": "10.0.1.15"},
    {"name": "process.name", "type_id": 9, "value": "powershell.exe"},
    {"name": "process.cmd_line", "type_id": 13, "value": "powershell -enc SQBFAFgA..."},
    {"name": "dst_endpoint.domain", "type_id": 1, "value": "c2.malicious.example"},
    {
      "name": "file.hashes[0]",
      "type_id": 8,
      "value": "e3b0c44298fc1c149afbf4c8996fb924",
      "reputation": {
        "score_id": 9,
        "score": "Probably Malicious",
        "provider": "VirusTotal",
        "base_score": 58.0
      }
    }
  ],
  "evidences": [
    {
      "process": {
        "name": "powershell.exe",
        "pid": 4832,
        "cmd_line": "powershell -enc SQBFAFgA...",
        "file": {
          "name": "powershell.exe",
          "path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
          "hashes": [
            {
              "algorithm_id": 3,
              "algorithm": "SHA-256",
              "value": "abc123def456..."
            }
          ]
        },
        "parent_process": {
          "name": "cmd.exe",
          "pid": 3210
        }
      },
      "device": {
        "hostname": "WORKSTATION-42",
        "ip": "10.0.1.15",
        "type_id": 2,
        "os": {
          "name": "Windows",
          "version": "10.0.19045"
        }
      },
      "user": {
        "name": "jdoe",
        "uid": "S-1-5-21-123456789-1234-5678",
        "type_id": 1
      },
      "verdict_id": 2,
      "verdict": "True Positive"
    }
  ],
  "device": {
    "hostname": "WORKSTATION-42",
    "ip": "10.0.1.15",
    "uid": "device-ws42",
    "type_id": 2,
    "os": {
      "name": "Windows",
      "version": "10.0.19045"
    }
  },
  "risk_level_id": 3,
  "risk_level": "High",
  "risk_score": 85
}
```

---

## Cloud Detection (AWS GuardDuty)

AWS GuardDuty finding mapped to OCSF with Cloud profile.

```json
{
  "activity_id": 1,
  "category_uid": 2,
  "class_uid": 2004,
  "type_uid": 200401,
  "severity_id": 4,
  "severity": "High",
  "time": 1711756800000,
  "confidence_id": 2,
  "confidence": "Medium",
  "status_id": 1,
  "is_alert": true,
  "message": "EC2 instance communicating with known cryptocurrency mining pool",
  "metadata": {
    "product": {
      "name": "GuardDuty",
      "vendor_name": "AWS",
      "version": "2.0",
      "uid": "guardduty"
    },
    "version": "1.8.0",
    "uid": "gd-evt-99887766",
    "profiles": ["Cloud", "Security Control"],
    "tenant_uid": "123456789012"
  },
  "finding_info": {
    "uid": "arn:aws:guardduty:us-east-1:123456789012:detector/abc/finding/def",
    "title": "CryptoCurrency:EC2/BitcoinTool.B!DNS",
    "desc": "EC2 instance i-0abc123 is querying a domain associated with Bitcoin mining",
    "analytic": {
      "name": "CryptoCurrency:EC2/BitcoinTool.B!DNS",
      "uid": "gd-type-cryptomining-dns",
      "type_id": 1,
      "type": "Rule"
    },
    "attacks": [
      {
        "tactic": {"uid": "TA0040", "name": "Impact"},
        "technique": {"uid": "T1496", "name": "Resource Hijacking"},
        "version": "v14"
      }
    ],
    "src_url": "https://us-east-1.console.aws.amazon.com/guardduty/home?region=us-east-1#/findings?fId=def",
    "created_time": 1711756800000
  },
  "observables": [
    {"name": "resources[0].uid", "type_id": 10, "value": "i-0abc123def456"},
    {"name": "src_endpoint.ip", "type_id": 2, "value": "10.0.5.77"},
    {"name": "dst_endpoint.domain", "type_id": 1, "value": "pool.bitcoin.example"}
  ],
  "resources": [
    {
      "uid": "arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123def456",
      "type": "AwsEc2Instance",
      "cloud_partition": "aws",
      "region": "us-east-1",
      "labels": [{"name": "env", "value": "production"}]
    }
  ]
}
```

---

## Update Event (Status Change)

Move a finding from New to In Progress with a comment (`activity_id: 2`).

```json
{
  "activity_id": 2,
  "activity_name": "Update",
  "category_uid": 2,
  "class_uid": 2004,
  "type_uid": 200402,
  "severity_id": 4,
  "time": 1711760400000,
  "status_id": 2,
  "status": "In Progress",
  "comment": "Assigned to SOC analyst for investigation - ticket INC-5678",
  "metadata": {
    "product": {
      "name": "SOAR Platform",
      "vendor_name": "SecOps Inc",
      "version": "4.0"
    },
    "version": "1.8.0"
  },
  "finding_info": {
    "uid": "DET-2024-0042",
    "title": "PowerShell Download Cradle",
    "modified_time": 1711760400000
  }
}
```

---

## Close Event

Resolve a finding as a true positive with remediation details (`activity_id: 3`).

```json
{
  "activity_id": 3,
  "activity_name": "Close",
  "category_uid": 2,
  "class_uid": 2004,
  "type_uid": 200403,
  "severity_id": 4,
  "time": 1711846800000,
  "status_id": 4,
  "status": "Resolved",
  "status_detail": "True positive confirmed. Host reimaged, credentials rotated.",
  "comment": "Incident INC-5678 closed. Root cause: phishing email with malicious macro.",
  "metadata": {
    "product": {
      "name": "SOAR Platform",
      "vendor_name": "SecOps Inc",
      "version": "4.0"
    },
    "version": "1.8.0"
  },
  "finding_info": {
    "uid": "DET-2024-0042",
    "title": "PowerShell Download Cradle",
    "modified_time": 1711846800000
  },
  "remediation": {
    "desc": "Reimage affected host, rotate all credentials for user jdoe, block C2 domain at perimeter firewall.",
    "references": [
      "https://wiki.internal.example/playbooks/powershell-download-cradle",
      "https://attack.mitre.org/mitigations/M1038/"
    ]
  }
}
```

---

## Common Mapping Patterns

### Vendor Alert → OCSF Detection Finding

| Vendor Field | OCSF Attribute | Notes |
|-------------|----------------|-------|
| Alert ID / Finding ID | `finding_info.uid` | Required — unique per finding |
| Alert title / Rule name | `finding_info.title` | Human-readable summary |
| Alert description | `finding_info.desc` or `message` | Use `message` for source-reported text |
| Rule ID / Signature ID | `finding_info.analytic.uid` | Detection rule identifier |
| Rule name | `finding_info.analytic.name` | Detection rule name |
| Alert severity (string) | `severity` + `severity_id` | Normalize to 0–6 scale |
| Alert status | `status` + `status_id` | Normalize to lifecycle enum |
| Timestamp | `time` | Epoch ms or RFC 3339 |
| Source IP | `observables[]` with `type_id: 2` | Also in evidence `src_endpoint.ip` |
| Destination IP | `observables[]` with `type_id: 2` | Also in evidence `dst_endpoint.ip` |
| File hash | `observables[]` with `type_id: 8` | Also in evidence `file.hashes[]` |
| MITRE technique | `finding_info.attacks[].technique` | Include `uid` and `name` |
| Raw log | `raw_data` | Original source payload |

### Severity Mapping Guide

| Source Severity | Recommended `severity_id` |
|----------------|--------------------------|
| info, informational, notice | 1 (Informational) |
| low, minor, warning | 2 (Low) |
| medium, moderate | 3 (Medium) |
| high, major | 4 (High) |
| critical, severe, urgent | 5 (Critical) |
| fatal, emergency, panic | 6 (Fatal) |
| unknown, none, unspecified | 0 (Unknown) |

### Status Mapping Guide

| Source Status | Recommended `status_id` |
|--------------|------------------------|
| new, open, created, pending | 1 (New) |
| in_progress, investigating, assigned, acknowledged | 2 (In Progress) |
| suppressed, muted, silenced, tuned, whitelisted | 3 (Suppressed) |
| resolved, closed, fixed, remediated | 4 (Resolved) |
| archived, retained | 5 (Archived) |
| deleted, removed, purged | 6 (Deleted) |
