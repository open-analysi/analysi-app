# OCSF Alert Structure — Evidence, Observables, Actor, Device

This reference covers the OCSF Detection Finding objects that carry alert data. Cy scripts access these through **helper functions** rather than navigating raw OCSF paths.

## Observables (IOC Pointers)

`observables[]` is a flat list of indicators found in the alert. Each entry has a `type_id` (integer) and `value` (string). The helpers map `type_id` to short names like `"ip"`, `"domain"`, etc.

**OCSF structure:**
```json
{
  "observables": [
    {"type_id": 2, "type": "IP Address", "value": "203.0.113.50"},
    {"type_id": 1, "type": "Hostname", "value": "evil.example.com"},
    {"type_id": 8, "type": "Hash", "value": "d41d8cd98f00b204e9800998ecf8427e"}
  ]
}
```

**Type ID mapping:**

| type_id | OCSF Name | Helper short name |
|---------|-----------|-------------------|
| 1 | Hostname | `"domain"` |
| 2 | IP Address | `"ip"` |
| 5 | Email Address | `"email"` |
| 6 | URL String | `"url"` |
| 7 | File Name | `"filename"` |
| 8 | Hash | `"filehash"` |
| 9 | Process Name | `"process"` |

**Cy access patterns:**
```cy
# Get all observables
all_obs = get_observables(input)

# Filter by type
ips = get_observables(input, type="ip")
domains = get_observables(input, type="domain")
urls = get_observables(input, type="url")
hashes = get_observables(input, type="filehash")

# Get primary (first) observable
ioc_value = get_primary_observable_value(input) ?? ""
ioc_type = get_primary_observable_type(input) ?? "unknown"

# Iterate with type filtering
for obs in get_observables(input, type="ip") {
    ip = obs.value
    result = app::virustotal::ip_reputation(ip=ip)
}

# Lookup each type
for obs in get_observables(input, type="filehash") {
    result = app::virustotal::file_report(hash=obs.value)
}
for obs in get_observables(input, type="url") {
    result = app::urlscan::scan_url(url=obs.value)
}
for obs in get_observables(input, type="domain") {
    result = app::virustotal::domain_report(domain=obs.value)
}
```

---

## Evidences (Rich Artifacts)

`evidences[]` contains detailed evidence objects with typed sub-structures. Each evidence can have network endpoints, processes, files, URLs, HTTP data, and more.

**OCSF structure:**
```json
{
  "evidences": [
    {
      "src_endpoint": {"ip": "203.0.113.50", "port": 54321, "hostname": "attacker.example.com"},
      "dst_endpoint": {"ip": "10.0.1.100", "port": 443, "hostname": "webserver-01"},
      "process": {
        "name": "powershell.exe",
        "cmd_line": "powershell -enc SQBFAFgA...",
        "pid": 2476,
        "file": {"name": "powershell.exe", "path": "C:\\Windows\\System32\\powershell.exe"},
        "parent_process": {"name": "cmd.exe", "pid": 1234, "cmd_line": "cmd.exe /c ..."},
        "user": {"name": "Administrator"}
      },
      "file": {
        "name": "malware.exe",
        "path": "C:\\temp\\malware.exe",
        "size": 45056,
        "hashes": [{"algorithm": "SHA-256", "value": "abc123..."}],
        "type_id": 1
      },
      "url": {"url_string": "https://example.com/api?id=1", "path": "/api", "query_string": "id=1"},
      "http_request": {"http_method": "POST", "user_agent": "curl/7.68.0"},
      "http_response": {"code": 200}
    }
  ]
}
```

### Network Data (src_endpoint / dst_endpoint)

Use helpers for common fields:

```cy
# Common access via helpers
src_ip = get_src_ip(input) ?? "unknown"
dst_ip = get_dst_ip(input) ?? "unknown"

# When populated: Firewall logs, IDS/IPS, EDR network events, VPC flow logs
# When null: Authentication events, file-only events, policy violations
```

### Process Data (process)

Access via evidence:

```cy
# Access process info from first evidence
ev = (input.evidences[0]) ?? {}
proc = ev.process ?? {}
proc_name = proc.name ?? "unknown"
cmd = proc.cmd_line ?? ""
user = (proc.user.name) ?? ""

# Parent process chain
parent = proc.parent_process ?? {}
parent_name = parent.name ?? ""
parent_cmd = parent.cmd_line ?? ""

# Process hash
proc_file = proc.file ?? {}
proc_hashes = proc_file.hashes ?? []

# When populated: EDR alerts, Sysmon, Windows Security 4688, endpoint telemetry
# When null: Network-only alerts, cloud/IAM events, email events
```

### File Data (file)

Access via evidence:

```cy
ev = (input.evidences[0]) ?? {}
file = ev.file ?? {}
filename = file.name ?? "unknown"
filepath = file.path ?? ""
size = file.size ?? 0
hashes = file.hashes ?? []

# Get best available hash
hash_value = ""
for h in hashes {
    if h.algorithm == "SHA-256" { hash_value = h.value }
}

# When populated: DLP alerts, file transfer events, AV detections, EDR file events
# When null: Network-only events, authentication events
```

### URL / HTTP Data (url, http_request, http_response)

Use helpers for common fields:

```cy
# Common access via helpers
url = get_url(input) ?? ""
path = get_url_path(input) ?? ""

# Additional HTTP detail from evidence
ev = (input.evidences[0]) ?? {}
req = ev.http_request ?? {}
method = req.http_method ?? "GET"
user_agent = req.user_agent ?? ""
resp = ev.http_response ?? {}
status = resp.code ?? 0

# When populated: WAF alerts, web proxy logs, HTTP inspection, URL filtering
# When null: Non-HTTP traffic, endpoint-only events, auth without web context
```

---

## Actor (User)

`actor` identifies the user who triggered the event.

**OCSF structure:**
```json
{
  "actor": {
    "user": {"name": "jdoe", "uid": "jdoe", "email_addr": "jdoe@corp.com"},
    "session": {"uid": "session-123"}
  }
}
```

```cy
# Via helpers (preferred)
user = get_primary_user(input) ?? "unknown_user"
entity_type = get_primary_entity_type(input)  # "user" if actor present

# Direct access when you need more fields
actor = input.actor ?? {}
user_obj = actor.user ?? {}
email = user_obj.email_addr ?? ""
```

---

## Device

`device` identifies the host/device involved.

**OCSF structure:**
```json
{
  "device": {
    "hostname": "ws-001",
    "name": "Workstation 001",
    "ip": "10.0.1.50",
    "os": {"name": "Windows", "version": "11"},
    "type": "Desktop"
  }
}
```

```cy
# Via helpers (preferred)
device = get_primary_device(input) ?? "unknown_host"
entity_type = get_primary_entity_type(input)  # "device" if no actor.user

# Direct access when you need more fields
dev = input.device ?? {}
os_name = (dev.os.name) ?? ""
device_type = dev.type ?? ""
```

---

## Vulnerabilities (CVE Data)

Use the `get_cve_ids()` helper.

**OCSF structure:**
```json
{
  "vulnerabilities": [
    {
      "cve": {"uid": "CVE-2021-44228", "cvss": [{"base_score": 10.0, "severity": "Critical"}]},
      "kb_articles": ["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"]
    }
  ]
}
```

```cy
# Via helper
cve_ids = get_cve_ids(input)  # ["CVE-2021-44228"]

# Check for specific CVE
if "CVE-2021-44228" in cve_ids {
    # Log4Shell handling
}

# When populated: Vulnerability scanners, EDR exploit detection, WAF exploit attempts
# When null: General security events, auth events, data loss events
```

---

## Metadata & Labels

`metadata` carries product info and free-form labels. Labels use `"key:value"` format.

**OCSF structure:**
```json
{
  "metadata": {
    "product": {"vendor_name": "Splunk", "name": "Enterprise Security"},
    "labels": ["source_category:EDR", "environment:production"],
    "version": "1.8.0"
  }
}
```

```cy
# Via helper
category = get_label(input, "source_category") ?? "unknown"
env = get_label(input, "environment") ?? ""

# Direct access
vendor = (input.metadata.product.vendor_name) ?? "unknown"
product_name = (input.metadata.product.name) ?? "unknown"
```

---

## Finding Info

`finding_info` contains the detection finding metadata.

**IMPORTANT:** `finding_info.title` is the alert title (human-readable summary). The detection **rule name** lives in `finding_info.analytic.name`. These are different — titles can vary per alert instance (e.g., "Suspicious login from 185.220.101.45"), while `analytic.name` is stable across all alerts from the same detection rule (e.g., "SOC165 - Possible SQL Injection Payload Detected"). Alert routing uses `rule_name` / `analytic.name`, never `title`.

```cy
title = input.finding_info.title ?? input.title ?? "unknown alert"
rule_name = input.rule_name ?? input.finding_info.analytic.name ?? ""
uid = input.finding_info.uid ?? ""
```

---

## Quick Reference: OCSF Helper Functions

| Purpose | Helper call |
|---------|------------|
| Primary entity type (user/device) | `get_primary_entity_type(input)` |
| Primary entity value | `get_primary_entity_value(input)` |
| Primary observable type (ip/domain/url) | `get_primary_observable_type(input)` |
| Primary observable value | `get_primary_observable_value(input)` |
| All observables (with optional type filter) | `get_observables(input)` / `get_observables(input, type="ip")` |
| Source IP | `get_src_ip(input)` |
| Destination IP | `get_dst_ip(input)` |
| URL | `get_url(input)` |
| URL path | `get_url_path(input)` |
| CVE IDs | `get_cve_ids(input)` |
| Metadata label | `get_label(input, "source_category")` |

## See Also

- `ocsf_schema_overview.md` — Full helper function reference and top-level structure
- `ocsf_enrichment_pattern.md` — How to add enrichments to alerts
