---
detection_rule: Possible SQL Injection Payload Detected
alert_type: Web Attack
subcategory: SQL Injection
source_category: WAF
mitre_tactics: [T1190, T1059]
integrations_required: [siem]
integrations_optional: [threat_intel, edr]
version: 1.0.0
author: runbook-agent
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
      "time": "2026-04-26T11:34:00Z",
      "message": "Possible SQL Injection Payload Detected",
      "finding_info": {
        "title": "Possible SQL Injection Payload Detected",
        "desc": "Requested URL Contains OR 1 = 1",
        "uid": "18fc0dda-6d47-4f50-911e-37ec10a3cb5d",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "Possible SQL Injection Payload Detected",
          "type_id": 1,
          "type": "Rule"
        }
      },
      "metadata": {
        "version": "1.8.0",
        "product": {
          "name": "Security Detection",
          "vendor_name": "Unknown"
        },
        "labels": [
          "source_category:WAF"
        ]
      },
      "device": {
        "hostname": "WebServer1001",
        "name": "WebServer1001"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "91.234.56.17"
        },
        {
          "name": "dest_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "10.10.20.18"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://10.10.20.18/search/?q=%22%20OR%201%20%3D%201%20--%20-"
        },
        {
          "name": "user_agent",
          "type_id": 16,
          "type": "HTTP User-Agent",
          "value": "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1"
        }
      ],
      "evidences": [
        {
          "src_endpoint": {"ip": "91.234.56.17"},
          "dst_endpoint": {"ip": "10.10.20.18"},
          "url": {"url_string": "https://10.10.20.18/search/?q=%22%20OR%201%20%3D%201%20--%20-"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1"
          }
        }
      ],
      "raw_data": "Rule : Possible SQL Injection Payload Detected\nSeverity : High\nType : Web Attack\nEvent Time : Feb, 25, 2022, 11:34 AM\nHostname : WebServer1001\nDestination IP Address : 10.10.20.18\nSource IP Address : 91.234.56.17\nHTTP Request Method : GET\nRequested URL : https://10.10.20.18/search/?q=%22%20OR%201%20%3D%201%20--%20-\nUser-Agent : Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1\nAlert Trigger Reason : Requested URL Contains OR 1 = 1\nDevice Action : Allowed",
      "unmapped": {
        "alert_trigger_reason": "Requested URL Contains OR 1 = 1"
      }
    }
---
# Possible SQL Injection Payload Detected Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

![[common/by_source/waf-siem-evidence.md]]

![[common/by_type/sql-injection-analysis.md]]

![[common/evidence/threat-intel-enrichment.md]]

### 5. Attack Success Determination ★
- **Action:** Determine if SQL injection succeeded based on response patterns
- **Depends On:** Steps 2a, 2c, 3
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.sqli_payload_analysis, outputs.http_events
- **Decision Points:**
  - `unique_sizes == 1 AND all statuses == 500` → Unsuccessful (application error response pattern, example: 948 bytes consistently)
  - `unique_sizes > 5 AND any status == 200` → Likely successful extraction (varying response sizes indicate different data returned)
  - `event_count > 50 in 30min` → Automated scanner behavior
  - `event_count < 10 AND sophisticated payloads` → Targeted manual attack
  - `max_size >> avg_size` → Potential large data extraction
  - `Normal request (200) followed by injection attempts (500)` → Attack progression pattern
- **Output:** sqli_attack_verdict

### 6. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 4a (optional), 5
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.sqli_attack_verdict, outputs.sqli_payload_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 7. Impact Assessment
- **Action:** Determine actual and potential impact
- **Depends On:** Steps 5, 6
- **Pattern:** impact_assessment
- **Input:** outputs.sqli_attack_verdict, outputs.validated_hypothesis
- **Focus:** Data exposure risk, database compromise indicators, compliance implications, need for database audit logs
- **Output:** sqli_impact_assessment

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "SQL injection from ${get_src_ip(alert)} - [successful|unsuccessful] - [data exposed|no data exposed]"

## Conditional Logic

### Branch: Successful Data Extraction
- **Condition:** outputs.sqli_attack_verdict.succeeded == true AND outputs.response_patterns.max_size > 50000
- **Additional Steps:**
  - Query database logs for accessed tables
  - Check for data exfiltration indicators
  - Search for webshell installation attempts
  - Immediate escalation to incident response

### Branch: Unsuccessful Attack Pattern
- **Condition:** outputs.response_patterns.unique_sizes == 1 AND ALL outputs.response_patterns.statuses == 500
- **Fast Track:** True Positive but unsuccessful - no data extracted, proceed to disposition without escalation

### Branch: Security Scanner Detected
- **Condition:** outputs.validated_hypothesis == "Automated SQL injection scanner" AND outputs.http_events.count > 100
- **Additional Steps:**
  - Verify if authorized security testing
  - Check scan schedule against detected time
  - Lower severity if authorized

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR outputs.abuse_history == null
- **Verification Steps:**
  - Check IT change management tickets for scheduled security assessments
  - Verify source IP matches known security vendor ranges
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate for unauthorized testing

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for attack pattern and success determination
2. **URL decoding:** Critical for understanding actual SQL injection technique
3. **Response pattern analysis:** Definitive indicator of attack success/failure
4. **Threat intelligence:** Context for attacker profile and risk assessment

### Common Patterns
- **Automated scanners:** High volume (50+ requests), multiple payload types, consistent timing
- **Manual testing:** Low volume (5-20 requests), progressive complexity, irregular timing
- **Successful injection:** Varying response sizes with 200 status codes
- **Blocked injection:** Consistent error responses (500/403), uniform response sizes

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 4a, 4b can run in parallel (threat intel lookups)
- Critical path: 1 → 2 → 3 → 5 → 6 → 8a → 8b
- Optional enrichment: 4a, 4b, 7
