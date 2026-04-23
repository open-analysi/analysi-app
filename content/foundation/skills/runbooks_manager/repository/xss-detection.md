---
detection_rule: Javascript Code Detected in Requested URL
alert_type: Web Attack
subcategory: XSS
source_category: WAF
mitre_tactics: [T1189, T1059]
integrations_required: [siem]
integrations_optional: [threat_intel]
version: 1.0.0
last_updated: 2025-11-16
author: ld-runbook-agent
source: soc166
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
      "severity_id": 3,
      "severity": "Medium",
      "status_id": 1,
      "status": "New",
      "time": "2022-02-26T18:56:00Z",
      "message": "Javascript Code Detected in Requested URL",
      "finding_info": {
        "title": "Javascript Code Detected in Requested URL",
        "desc": "Javascript code detected in URL",
        "uid": "c76c890a-bb39-4cc6-abcf-e9d65b4f64f0",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "SOC166 - Javascript Code Detected in Requested URL",
          "type_id": 1,
          "type": "Rule"
        }
      },
      "metadata": {
        "version": "1.8.0",
        "product": {
          "name": "HTTP Parsing Firewall",
          "vendor_name": "Firewall"
        },
        "labels": [
          "source_category:WAF"
        ]
      },
      "action_id": 1,
      "action": "Allowed",
      "disposition_id": 1,
      "disposition": "Allowed",
      "device": {
        "hostname": "WebServer1002",
        "name": "WebServer1002",
        "ip": "172.16.17.17"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "112.85.42.13"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://172.16.17.17/search/?q=<$script>javascript:$alert(1)<$/script>"
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
          "src_endpoint": {"ip": "112.85.42.13"},
          "dst_endpoint": {"ip": "172.16.17.17"},
          "url": {"url_string": "https://172.16.17.17/search/?q=<$script>javascript:$alert(1)<$/script>"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1"
          }
        }
      ],
      "raw_data": "Rule : SOC166 - Javascript Code Detected in Requested URL\nSeverity : Medium\nType : Web Attack\nEvent Time : Feb, 26, 2022, 06:56 PM\nHostname : WebServer1002\nDestination IP Address : 172.16.17.17\nSource IP Address : 112.85.42.13\nHTTP Request Method : GET\nRequested URL : https://172.16.17.17/search/?q=<$script>javascript:$alert(1)<$/script>\nUser-Agent : Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1\nAlert Trigger Reason : Javascript code detected in URL\nDevice Action : Allowed",
      "unmapped": {
        "alert_trigger_reason": "Javascript code detected in URL",
        "log_source": "HTTP Firewall Logs"
      }
    }
---
# Javascript Code Detected in Requested URL Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

![[common/by_source/waf-siem-evidence.md]]

![[common/by_type/xss-payload-analysis.md]]

![[common/evidence/threat-intel-enrichment.md]]

### 5. Attack Success Determination ★
- **Action:** Determine if XSS injection succeeded based on response patterns
- **Depends On:** Steps 2a, 2c, 3
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.xss_payload_analysis, outputs.http_events
- **Decision Points:**
  - `all statuses == 302 AND response_sizes == 0` → Unsuccessful (redirected before execution, example pattern from investigation)
  - `status == 200 AND response_size > 0` → Potentially successful (payload reflected in response)
  - `status == 403/blocked` → WAF blocked
  - `event_count > 20 in short timeframe` → Automated fuzzer behavior
  - `event_count < 10 AND diverse payloads` → Manual targeted testing
  - `Normal request (200) followed by injection attempts (302/403)` → Attack reconnaissance pattern
- **Output:** xss_attack_verdict

### 6. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 4a (optional), 5
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.xss_attack_verdict, outputs.xss_payload_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 7. Impact Assessment
- **Action:** Determine actual and potential impact
- **Depends On:** Steps 5, 6
- **Pattern:** impact_assessment
- **Input:** outputs.xss_attack_verdict, outputs.validated_hypothesis
- **Focus:** Session hijacking risk, credential theft potential, defacement possibility, stored vs reflected XSS, user data exposure
- **Output:** xss_impact_assessment

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "XSS attempt from ${get_src_ip(alert)} - [successful|unsuccessful] - [payload reflected|blocked]"

## Conditional Logic

### Branch: Successful XSS Injection
- **Condition:** outputs.xss_attack_verdict.succeeded == true AND outputs.response_patterns.status == 200
- **Additional Steps:**
  - Check for stored XSS (payload persistence)
  - Review session logs for potential hijacking
  - Search for credential theft indicators
  - Check for additional malicious payloads from same IP
  - Immediate escalation to incident response

### Branch: Unsuccessful Attack Pattern
- **Condition:** outputs.response_patterns.all_statuses == 302 OR outputs.response_patterns.all_statuses == 403
- **Fast Track:** True Positive but unsuccessful - payload blocked/redirected, proceed to disposition without escalation

### Branch: Security Scanner Detected
- **Condition:** outputs.validated_hypothesis == "Automated XSS scanner" AND outputs.http_events.count > 20
- **Additional Steps:**
  - Verify if authorized security testing
  - Check scan schedule against detected time
  - Lower severity if authorized

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR source IP matches known testing ranges
- **Verification Steps:**
  - Check IT change management tickets for scheduled security assessments
  - Verify source IP matches known security vendor ranges
  - Contact security team or review internal communication channels
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate for unauthorized testing

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for attack pattern and success determination
2. **URL decoding:** Critical for understanding actual XSS injection technique
3. **Response pattern analysis:** Definitive indicator of attack success/failure (200 vs 302/403)
4. **Response size analysis:** Zero-size responses indicate redirection before payload execution
5. **Threat intelligence:** Context for attacker profile and risk assessment

### Common XSS Patterns
- **Automated scanners:** High volume (20+ requests), multiple payload types (script tags, event handlers, SVG), consistent timing
- **Manual testing:** Low volume (5-15 requests), progressive complexity, irregular timing
- **Successful injection:** 200 status with non-zero response size containing reflected payload
- **Blocked injection:** 302 redirects, 403 forbidden, or consistent zero-byte responses

### Attack Progression Indicators
1. **Normal browsing:** 200 status with normal response sizes
2. **Test payload:** Simple "test" parameter to verify parameter reflection
3. **XSS probing:** Various XSS vectors (script tags, event handlers, javascript: protocol)
4. **Success indicator:** 200 response with payload reflected vs 302/403 blocked

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 4a, 4b can run in parallel (threat intel lookups)
- Critical path: 1 → 2 → 3 → 5 → 6 → 8a → 8b
- Optional enrichment: 4a, 4b, 7
