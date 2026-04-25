---
detection_rule: "Suspicious DNS Query Volume with Encoded Subdomains Detected"
alert_type: "Data Exfiltration"
subcategory: "DNS Tunneling"
source_category: "Network"
mitre_tactics: [T1048, T1071]
integrations_required: [siem]
integrations_optional: [threat_intel, edr]
version: "1.0.0"
author: "runbook-match-agent"
source: "composed"
composition_metadata:
  confidence: VERY LOW
  primary_source: "universal components only"
  blended_from:
    - file: "common/universal/alert-understanding.md"
      sections: [1]
      reason: "Standard alert intake and hypothesis formation"
    - file: "common/evidence/threat-intel-enrichment.md"
      sections: [3]
      reason: "Domain and IP reputation enrichment"
    - file: "common/universal/final-analysis-trio.md"
      sections: [final]
      reason: "Standard verdict and disposition workflow"
    - file: "cybersecurity-analyst/references/network-traffic-analysis.md"
      sections: ["DNS Tunneling", "Beaconing Detection", "Data Exfiltration"]
      reason: "DNS tunneling investigation patterns — no repository runbook exists"
  gaps_identified:
    - "No DNS tunneling runbook in repository"
    - "No Data Exfiltration alert_type runbooks exist"
    - "No Network source_category runbooks exist — all existing are WAF or Identity"
    - "No MITRE T1048 (Exfiltration over Alternative Protocol) or T1071 (Application Layer Protocol) runbooks"
    - "No by_type/ pattern for DNS tunneling or covert channel analysis"
  review_required: true
alert_examples:
  - |
    {
      "class_uid": 2004,
      "class_name": "Detection Finding",
      "category_uid": 2,
      "category_name": "Findings",
      "activity_id": 1,
      "activity_name": "Create",
      "type_uid": 200401,
      "type_name": "Detection Finding: Create",
      "severity_id": 4,
      "severity": "High",
      "status_id": 1,
      "status": "New",
      "time": "2026-04-26T08:22:00Z",
      "message": "Suspicious DNS Query Volume with Encoded Subdomains Detected",
      "finding_info": {
        "title": "Suspicious DNS Query Volume with Encoded Subdomains Detected",
        "uid": "f4e29a11-83b7-4d0c-a5e1-9c1742dbe803",
        "types": [
          "Data Exfiltration"
        ],
        "analytic": {
          "name": "dns_tunneling_exfiltration",
          "type_id": 1,
          "type": "Rule"
        },
        "desc": "Internal host generated an anomalous volume of DNS queries with high-entropy encoded subdomains targeting a single external domain. Pattern is consistent with DNS tunneling used for data exfiltration or C2 communication."
      },
      "metadata": {
        "version": "1.8.0",
        "product": {
          "name": "Security Detection",
          "vendor_name": "Unknown"
        },
        "labels": [
          "source_category:Network"
        ]
      },
      "device": {
        "hostname": "WKSTN-FIN-042",
        "name": "WKSTN-FIN-042",
        "ip": "10.20.30.42"
      },
      "evidences": [
        {
          "src_endpoint": {"ip": "10.20.30.42"},
          "dst_endpoint": {"domain": "c2.evil.example.com"}
        }
      ],
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "10.20.30.42"
        },
        {
          "name": "dst_domain",
          "type_id": 1,
          "type": "Hostname",
          "value": "c2.evil.example.com"
        }
      ],
      "unmapped": {
        "query_volume": 4782,
        "subdomain_patterns": ["dGhlIHF1aWNr.c2.evil.example.com", "YnJvd24gZm94.c2.evil.example.com", "anVtcHMgb3Zlcg.c2.evil.example.com"]
      },
      "raw_data": "Rule : dns_tunneling_exfiltration\nSeverity : High\nType : Data Exfiltration\nEvent Time : Mar, 10, 2024, 08:22 AM\nSource IP : 10.20.30.42\nHostname : WKSTN-FIN-042\nTarget Domain : c2.evil.example.com\nQuery Volume : 4782 queries in 30 minutes\nSubdomain Entropy : 4.8 bits/char\nQuery Types : A, TXT\nAlert Trigger Reason : Anomalous DNS query volume with high-entropy encoded subdomains to a single external domain."
    }
---

# Suspicious DNS Query Volume with Encoded Subdomains Detected Investigation Runbook

## Steps

### 1. Alert Understanding & Initial Assessment ★
- **Action:** Analyze alert and form investigation hypotheses
- **Pattern:** hypothesis_formation
- **Input:** finding_info.title, severity, get_src_ip(alert), get_dst_domain(alert), unmapped.query_volume, unmapped.subdomain_patterns, finding_info.desc
- **Focus:** Identify the internal host generating anomalous DNS queries; note the target external domain; assess the encoded subdomain patterns for exfiltration signatures; hypothesize whether this is DNS tunneling (C2 or data exfiltration), legitimate monitoring tool (e.g., telemetry agent), or DNS-based DGA malware
- **Outputs:**
  - context_summary: Human-readable alert summary
  - investigation_hypotheses: List of theories — DNS tunneling exfiltration, C2 beaconing via DNS, compromised host with malware, misconfigured legitimate tool
  - key_observables: Source host IP/hostname, target domain, subdomain sample set, query volume rate

### 2. DNS Query Evidence Collection ★
- **Parallel:** Yes

#### 2a. DNS Log Analysis ★
- **Action:** Retrieve all DNS queries from the alerting host within the detection window and a ±30-minute lookback
- **Pattern:** integration_query
- **Integration:** siem
- **Fields:** get_src_ip(alert), time, get_dst_domain(alert)
- **Focus:** Total unique subdomain count; subdomain entropy and length distribution; query types (A, TXT, MX, CNAME — TXT is highest-risk for tunneling); query rate per minute; presence of base64/hex-encoded strings in subdomain labels; any direct DNS responses returning data payloads
- **Output:** dns_query_log

#### 2b. Host Network Context
- **Action:** Retrieve network flow records for the alerting host to understand all outbound connections during the alert window
- **Pattern:** integration_query
- **Integration:** siem
- **Fields:** get_src_ip(alert), time
- **Focus:** All outbound connections (not just DNS port 53); identify if there are corresponding TCP/UDP connections to the same external IP resolved from the tunneling domain; check for unusual destination ports or protocols alongside DNS traffic
- **Output:** network_flows

### 3. Subdomain Payload Analysis ★
- **Action:** Decode and analyze the subdomain strings from dns_query_log to characterize the exfiltration payload
- **Pattern:** payload_analysis
- **Input:** outputs.dns_query_log
- **Focus:** Attempt base64 decoding of subdomain labels; identify file headers, structured data, or plaintext content in decoded payloads; measure entropy of subdomain strings (high entropy > 4.0 bits/char = strong tunneling indicator); calculate average subdomain label length (>40 chars = tunneling); identify any sequencing patterns (counters, session IDs) suggesting chunked data transfer; estimate data volume = query_count × average_payload_size_per_label
- **Output:** payload_analysis

### 4. Threat Intelligence Enrichment
- **Parallel:** Yes
- **Optional:** Both sources can fail gracefully

#### 4a. Target Domain Reputation Check
- **Action:** Check the external tunneling domain's reputation and registration history
- **Purpose:** Validates whether the target domain is known malicious infrastructure or newly registered
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_dst_domain(alert) (data-sync.example.com or equivalent from alert)
- **Focus:** Domain age and registration date (newly registered = high suspicion); passive DNS history; known malware family associations; categorization (malware C2, data exfiltration, tunneling tool); hosting provider (bulletproof hosting?)
- **Output:** domain_reputation

#### 4b. Source Host IP Reputation Check
- **Action:** Check the alerting host's IP for prior threat intelligence hits
- **Purpose:** Determines if the host is a known compromised asset or previously seen in attacks
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** host_ip_reputation

### 5. Endpoint Investigation
- **Action:** Investigate the alerting host for malware, unauthorized processes, and persistence mechanisms
- **Pattern:** integration_query
- **Integration:** edr
- **Condition:** IF edr configured
- **Input:** outputs.dns_query_log, outputs.payload_analysis
- **Focus:** Identify the process responsible for DNS queries (process name, path, parent process, command line, binary hash); check if process is signed and known-good; look for persistence mechanisms (scheduled tasks, registry run keys, cron jobs, startup items); identify any recently downloaded or created files; check for tools associated with DNS tunneling (iodine, dnscat2, dns2tcp, custom scripts)
- **Output:** endpoint_telemetry

### 6. Attack Success & Data Exfiltration Assessment ★
- **Action:** Synthesize evidence to determine whether data exfiltration occurred and its scope
- **Pattern:** impact_assessment
- **Depends On:** Steps 2a, 2b, 3, 4a, 5
- **Input:** outputs.dns_query_log, outputs.payload_analysis, outputs.network_flows, outputs.endpoint_telemetry
- **Focus:** Calculate estimated data volume exfiltrated (query_count × payload_bytes); identify what data may have been exfiltrated (file contents, credentials, database records); determine exfiltration start time and duration; assess whether the channel is still active (ongoing vs historical); correlate with any data access events on the host or connected file shares/databases
- **Decision Points:**
  - `subdomain_entropy > 4.0 AND query_rate > 100/min AND target_domain is unknown` → Strong DNS tunneling indicator — TP
  - `decoded_payload contains file_header OR structured_data` → Confirmed data exfiltration — TP
  - `process = known_telemetry_agent AND domain = vendor_owned` → Legitimate monitoring tool — FP
  - `subdomain_labels are short AND low_entropy AND query_volume explained by TTL expiry` → Normal DNS behavior — FP
  - `edr detects iodine/dnscat2/dns2tcp` → Confirmed tunneling tool — TP, escalate
- **Output:** exfiltration_assessment

## Conditional Logic

### Branch: Confirmed DNS Tunneling Tool Detected
- **Condition:** `endpoint_telemetry.process_name IN ['iodine', 'dnscat2', 'dns2tcp'] OR endpoint_telemetry.binary_hash IN threat_intel.malware_hashes`
- **Additional Steps:** Immediate host isolation; preserve memory dump and disk image; escalate to IR team; identify all hosts that communicated with same tunneling domain
- **Escalation:** Critical — Active data exfiltration with known malware tooling

### Branch: High-Volume Exfiltration Confirmed
- **Condition:** `exfiltration_assessment.estimated_volume > 10MB OR exfiltration_assessment.duration > 30min`
- **Additional Steps:** Identify what sensitive data repositories the host had access to; notify data owners; assess regulatory notification requirements (GDPR, HIPAA, PCI-DSS)
- **Escalation:** High — Data breach assessment required

### Branch: Legitimate Monitoring Tool (FP)
- **Condition:** `endpoint_telemetry.process is signed AND domain_reputation.category = 'known_vendor' AND payload_analysis.decoded_content = telemetry_format`
- **Fast Track:** Confirm vendor, allowlist domain in DNS monitoring, close as FP with documentation
- **Skip:** Steps 5, 6 escalation path

### Branch: C2 Beaconing via DNS (No Exfiltration Yet)
- **Condition:** `payload_analysis shows command patterns OR C2 protocol indicators AND exfiltration_assessment.volume is low`
- **Additional Steps:** Check for lateral movement from the compromised host; investigate all systems that communicated with the same domain; search for initial access vector (phishing, exploit, malicious download)
- **Escalation:** High — Active C2 channel, containment required before exfiltration occurs

## Final Analysis

### Detailed Analysis ★
- **Action:** Comprehensive technical synthesis of the DNS tunneling investigation
- **Depends On:** All prior steps
- **Pattern:** threat_synthesis
- **Input:** ALL outputs
- **Focus:** Complete attack chain analysis — initial access → compromise → DNS tunneling tool deployment → data exfiltration; evidence correlation between DNS logs, endpoint telemetry, and decoded payloads; threat actor assessment; exfiltration scope and impact; recommended containment and remediation actions
- **Output:** detailed_analysis

### Disposition & Summary ★
- **Parallel:** Yes
- **Depends On:** Detailed Analysis
- **Actions:**
  - Determine verdict (TP/FP/Benign) with confidence score
  - Generate executive summary (128 chars max)
- **Pattern:** impact_assessment
- **Input:** outputs.detailed_analysis
- **Outputs:**
  - disposition: {verdict: "TP|FP|Benign", confidence: 0.0-1.0, escalate: true|false}
  - summary: "DNS tunneling from ${get_src_ip(alert)} to ${get_dst_domain(alert)} - [confirmed exfiltration|C2 channel|FP] - [impact description]"

## Investigation Notes

### DNS Tunneling Detection Patterns
- **High-entropy subdomains** (Shannon entropy > 4.0 bits/char): Base64/hex-encoded data being chunked into DNS labels
- **Excessive unique subdomains**: Legitimate domains use a small set of subdomains; tunneling generates thousands of unique ones
- **TXT record queries**: DNS TXT records can carry arbitrary data — preferred for bidirectional tunneling
- **Long subdomain labels**: DNS labels max at 63 chars; tunneling tools use near-maximum length
- **Single target domain**: All anomalous queries go to one domain (the tunnel endpoint)
- **Consistent query rate**: Beaconing pattern even without confirmed exfiltration

### Known DNS Tunneling Tools
- **iodine**: Tunnels IPv4 over DNS; creates a network interface; cross-platform
- **dnscat2**: Encrypted C2 channel over DNS; supports shell, file transfer, port forwarding
- **dns2tcp**: Relays TCP connections over DNS; used for covert tunneling
- **Custom scripts**: Python/Bash one-liners using base64 encoding and `nslookup`/`dig`

### Efficiency Notes
- DNS log analysis (Step 2a) and endpoint investigation (Step 5) are the highest-yield steps for rapid triage
- If EDR is unavailable, focus analysis on DNS query characteristics (Step 3) to distinguish tunneling from legitimate activity
- Domain reputation check (Step 4a) can short-circuit investigation: known malicious domain = TP escalation without full analysis
