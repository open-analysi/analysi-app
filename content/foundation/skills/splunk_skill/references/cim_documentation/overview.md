# CIM Field Mappings Overview

The Common Information Model (CIM) provides standardized field names across Splunk data models, enabling cross-dataset correlation, data normalization, and app compatibility.

## Data Model Categories

| Category | File | Data Models |
|----------|------|-------------|
| Security | `security-fields.md` | Alerts, Authentication, Data Loss Prevention, Endpoint, Event Signatures, Intrusion Detection, Malware, Vulnerabilities |
| Network | `network-fields.md` | Certificates, Network Resolution (DNS), Network Sessions, Network Traffic, Web |
| IT Operations | `it-operations-fields.md` | Change, Data Access, Databases, Inventory, Performance, Updates |
| Other | `other-fields.md` | Email, Interprocess Messaging, JVM, Splunk Audit Logs, TicketManagement |

---

## Common Cross-Model Fields

These fields appear across multiple data models and are key for correlation.

### Universal Fields (10+ Data Models)

| Field | Count | Primary Use |
|-------|-------|-------------|
| **action** | 12 | Event action or operation type |
| **dest** | 20 | Destination system/host |
| **dest_bunit** | 19 | Destination business unit |
| **dest_category** | 19 | Destination asset category |
| **dest_priority** | 19 | Destination asset priority |
| **src** | 14 | Source system/host |
| **src_bunit** | 13 | Source business unit |
| **src_category** | 14 | Source asset category |
| **src_priority** | 14 | Source asset priority |
| **tag** | 24 | Event classification tags |
| **user** | 19 | User account |
| **user_bunit** | 16 | User business unit |
| **user_category** | 16 | User category |
| **user_priority** | 16 | User priority |
| **vendor_product** | 18 | Vendor product name |

### Network-Related Fields

- **src_ip**, **dest_ip**: Network Sessions, Network Traffic, Inventory
- **src_mac**, **dest_mac**: Network Sessions, Network Traffic
- **src_port**, **dest_port**: Network Traffic, Certificates, Endpoint, DNS
- **protocol**: Change, Email, Network Traffic
- **bytes**, **bytes_in**, **bytes_out**: Network Traffic, Web

### Security-Related Fields

- **signature**: Alerts, Authentication, DLP, Email, Event Signatures, IDS, Malware, Network Sessions, Performance, Updates, Vulnerabilities
- **signature_id**: Alerts, Authentication, DLP, Email, Event Signatures, IDS, Malware, Network Sessions, Performance, Updates, Vulnerabilities
- **file_hash**: Email, Endpoint, Intrusion Detection, Malware, Updates
- **file_name**: Email, Endpoint, Intrusion Detection, Malware, Updates
- **file_path**: Endpoint, Intrusion Detection, Malware

### Endpoint Fields

- **process**, **process_id**, **process_name**, **process_path**: Endpoint, Email, Network Traffic, JVM
- **parent_process_***: Endpoint (parent process fields)
- **registry_***: Endpoint (registry operations)
- **service_***: Endpoint (service operations)

---

## Field Naming Conventions

| Prefix | Meaning |
|--------|---------|
| **src_** | Source-related fields (origin of activity) |
| **dest_** | Destination-related fields (target of activity) |
| **_bunit** | Business unit for asset/user |
| **_category** | Category classification for asset/user |
| **_priority** | Priority level for asset/user |
| **_id** | Identifier or unique reference |
| **file_** | File-related metadata |
| **process_** | Process-related information |
| **registry_** | Windows registry operations |
| **service_** | Service-related data |
| **ssl_** | SSL/TLS certificate details |
| **http_** | HTTP-specific fields |
| **message_** | Message queue/messaging data |

---

## Best Practices

1. **Use Common Fields for Correlation**: Leverage `dest`, `src`, `user`, `tag` for cross-dataset correlation

2. **Normalize to CIM**: Map data to CIM field names for compatibility with security apps (ES, InfoSec App, SSE)

3. **Priority Fields**: Fields with `_priority`, `_bunit`, `_category` suffixes enable asset-based correlation

4. **Field Aliasing**: Use field aliases rather than modifying data models when raw data doesn't match CIM fields

---

## Usage Examples

### Correlating Authentication and Network Events

```spl
index=main (sourcetype=windows OR sourcetype=firewall)
| eval user=coalesce(user, src_user)
| eval dest_ip=coalesce(dest_ip, dest)
| stats values(action) as actions, values(src_ip) as source_ips by user
```

### Cross-Data Model User Activity

```spl
| tstats summariesonly=true count from datamodel=Authentication by Authentication.user, Authentication.action
| rename Authentication.* as *
| append [
    | tstats summariesonly=true count from datamodel=Web by Web.user, Web.action
    | rename Web.* as *
]
| stats sum(count) as total by user, action
```

---

## Reference

Based on Splunk CIM version 6.0. For current documentation:
https://docs.splunk.com/Documentation/CIM/latest/User/Overview
