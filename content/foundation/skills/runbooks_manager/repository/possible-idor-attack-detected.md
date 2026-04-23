---
detection_rule: Possible IDOR Attack Detected
alert_type: Web Attack
subcategory: IDOR
source_category: WAF
mitre_tactics: [T1190, T1548]
integrations_required: [siem]
integrations_optional: [threat_intel]
version: 1.0.0
last_updated: 2025-11-16
author: ld-runbook-agent
source: soc169
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
      "time": "2022-02-28T22:48:00Z",
      "message": "Possible IDOR Attack Detected",
      "finding_info": {
        "title": "Possible IDOR Attack Detected",
        "desc": "consecutive requests to the same page",
        "uid": "e92903ce-7ce1-47d2-8bd6-c8035a5d2362",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "SOC169 - Possible IDOR Attack Detected",
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
      "device": {
        "hostname": "WebServer1005",
        "name": "WebServer1005",
        "ip": "172.16.17.15"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "134.209.118.137"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://172.16.17.15/get_user_info/"
        },
        {
          "name": "user_agent",
          "type_id": 16,
          "type": "HTTP User-Agent",
          "value": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 1.1.4322)"
        }
      ],
      "evidences": [
        {
          "src_endpoint": {"ip": "134.209.118.137"},
          "dst_endpoint": {"ip": "172.16.17.15"},
          "url": {"url_string": "https://172.16.17.15/get_user_info/"},
          "http_request": {
            "http_method": "POST",
            "user_agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 1.1.4322)"
          }
        }
      ],
      "raw_data": "Rule : SOC169 - Possible IDOR Attack Detected\nSeverity : High\nType : Web Attack\nEvent Time : Feb. 28, 2022, 10:48 p.m.\nHostname : WebServer1005\nDestination IP Address : 172.16.17.15\nSource IP Address : 134.209.118.137\nHTTP Request Method : POST\nRequested URL : https://172.16.17.15/get_user_info/\nUser-Agent : Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 1.1.4322)\nAlert Trigger Reason : consecutive requests to the same page\nDevice Action: Allowed",
      "unmapped": {
        "alert_trigger_reason": "consecutive requests to the same page",
        "log_source": "HTTP Firewall Logs"
      }
    }
---
# Possible IDOR Attack Detected Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

### 1b. IDOR Attack Context Analysis ★
- **Action:** Understand IDOR (Insecure Direct Object Reference) attack patterns and access control bypass indicators
- **Purpose:** Validates: "Authorized testing" vs "IDOR enumeration attack" vs "Benign repeated requests"
- **Pattern:** hypothesis_formation
- **Input:** get_url(alert), finding_info.desc, get_http_method(alert)
- **Focus:** IDOR enables unauthorized data access by manipulating request parameters (user IDs, account numbers, object references), attack pattern shows consecutive requests to same endpoint with varying parameters, common in REST APIs and web applications with predictable object identifiers
- **Output:** idor_context
- **Decision Points:**
  - Consecutive requests to same endpoint → IDOR enumeration pattern
  - URL contains ID parameters (user_id, account_id) → Direct object reference
  - Requests from external IP → Unauthorized access attempt
  - Requests from internal IP → Possible benign or authorized testing

![[common/by_source/waf-siem-evidence.md]]

![[common/by_type/access-control-analysis.md]]

### 4. Response Analysis for Access Control Bypass ★
- **Action:** Analyze HTTP response patterns to determine if unauthorized access succeeded
- **Depends On:** Steps 2a, 2c, 3
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.access_control_payload_analysis, outputs.http_events
- **Decision Points:**
  - `varying_response_sizes AND all status == 200` → Successful unauthorized access (different data returned for each ID)
  - `uniform_response_size AND all status == 200` → Access blocked or error page returned
  - `status == 403 OR 401` → Access control enforced (attack unsuccessful)
  - `status == 404` → Objects not found or access denied
  - `status == 200 AND varying sizes` → High confidence successful IDOR exploitation (example pattern)
- **Output:** access_control_verdict
- **Decision Points (Example Values):**
  - Response sizes vary significantly → Different user data returned
  - All 200 status codes → Requests not blocked by application
  - Uniform error responses → Access control working

![[common/evidence/threat-intel-enrichment.md]]

### 6. Attack Success Determination ★
- **Action:** Determine if IDOR attack succeeded in accessing unauthorized data
- **Depends On:** Steps 4, 5a (optional)
- **Pattern:** impact_assessment
- **Input:** outputs.access_control_verdict, outputs.access_control_payload_analysis, outputs.ip_reputation (if available)
- **Decision Points:**
  - `action == allowed AND varying_response_sizes == true AND status == 200` → Successful IDOR attack
  - `action == allowed AND uniform_response_size == true` → Access blocked at application layer
  - `action == blocked` → WAF prevented attack
  - `status == 403|401` → Access control enforced
  - `high_request_count AND varying_sizes` → Large-scale unauthorized data access
- **Output:** idor_attack_verdict

### 7. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 4, 6
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.idor_attack_verdict, outputs.access_control_payload_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 8. Data Exposure Assessment
- **Action:** Determine scope of unauthorized data access and potential data exposure
- **Depends On:** Steps 4, 6, 7
- **Pattern:** impact_assessment
- **Input:** outputs.access_control_verdict, outputs.access_control_payload_analysis, outputs.idor_attack_verdict
- **Focus:** Number of unique IDs accessed, data sensitivity (user info, financial data), compliance implications (PII exposure), lateral access potential
- **Output:** idor_data_exposure_impact
- **Decision Points:**
  - `IDs_accessed > 100` → Large-scale data exposure
  - `endpoint contains 'user' OR 'account'` → PII exposure risk
  - `varying_responses AND 200 codes` → Confirmed data disclosure
  - `Low ID count AND authorized test` → Limited impact

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "IDOR attack from ${get_src_ip(alert)} targeting ${get_url(alert)} - [successful|unsuccessful] - [data exposed|access denied]"

## Conditional Logic

### Branch: Successful IDOR Data Exposure
- **Condition:** outputs.idor_attack_verdict.succeeded == true AND outputs.access_control_verdict.varying_response_sizes == true
- **Critical Actions:**
  - Immediate blocking of source IP at WAF/firewall
  - Identify all accessed user/object IDs from request logs
  - Assess data sensitivity of exposed records
  - Check for data exfiltration or downloads
  - Notify affected users if PII exposed
  - Escalate to incident response team
  - Review application access control implementation
  - Apply emergency access control fixes if possible
  - Audit all endpoints for similar IDOR vulnerabilities

### Branch: Failed IDOR Attempt (Access Control Working)
- **Condition:** outputs.response_patterns.status IN [403, 401, 404] OR outputs.access_control_verdict.uniform_response_size == true
- **Fast Track:** True Positive (malicious intent) but unsuccessful
- **Actions:**
  - Block source IP at firewall
  - Monitor for follow-up attacks from different IPs
  - Verify access control mechanisms are functioning correctly
  - Review WAF rules effectiveness
  - Document attack pattern for future detection

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR get_src_ip(alert) IN internal_ranges
- **Verification Steps:**
  - Check IT change management for scheduled security assessments
  - Verify source IP matches known security vendor ranges or internal test systems
  - Contact security team to confirm authorization
  - Review test scope against detected access pattern
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate for unauthorized testing

### Branch: Automated IDOR Scanner
- **Condition:** outputs.access_control_payload_analysis.request_count > 50 AND outputs.access_control_payload_analysis.sequential_pattern == true
- **Assessment:** Automated IDOR enumeration tool detected
- **Actions:**
  - Immediate IP blocking at perimeter
  - Check for successful data access in high-volume requests
  - Review all accessed object IDs for sensitivity
  - Assess if rate limiting would have prevented attack
  - Recommend rate limiting implementation
  - Search for similar patterns from other IPs

### Branch: Limited Manual Testing
- **Condition:** outputs.access_control_payload_analysis.request_count < 10 AND outputs.access_control_payload_analysis.sequential_pattern == false
- **Assessment:** Manual IDOR testing or targeted access attempt
- **Actions:**
  - Review specific IDs accessed for targeting pattern
  - Check if accessed IDs correlate to high-value accounts
  - Assess attacker knowledge level (random vs targeted IDs)
  - Determine if this is reconnaissance for future attack
  - Block source IP and monitor for escalation

## Investigation Notes

### Key Evidence Sources
1. **WAF/SIEM HTTP logs:** Primary evidence for IDOR enumeration patterns and response analysis
2. **Response size analysis:** Critical indicator of successful unauthorized data access
3. **Parameter analysis:** Reveals attack sophistication (sequential vs targeted)
4. **Status code patterns:** Definitive proof of access control enforcement or bypass

### Common Patterns
- **Successful IDOR:** Status 200 with varying response sizes for different parameter values
- **Blocked IDOR:** Uniform response sizes (error page) or 403/401 status codes
- **Sequential enumeration:** Parameters incrementing (user_id=1, user_id=2, user_id=3...)
- **Automated tools:** High volume (50+ requests in short time), perfect sequential pattern
- **Manual testing:** Lower volume (5-20 requests), irregular timing, possible non-sequential

### Critical Indicators
- **High Priority:** Varying response sizes with 200 status (confirmed unauthorized access)
- **High Priority:** High request count (100+) with successful access (large data exposure)
- **Medium Priority:** Sequential ID enumeration pattern (systematic attack)
- **Medium Priority:** Endpoint contains PII (user_info, account, profile)
- **Low Priority:** Single or few requests with access denied

### IDOR Attack Context
- **Vulnerability Type:** Broken Access Control (OWASP Top 10 #1)
- **Attack Vector:** Manipulate direct object references in URLs or request parameters to access unauthorized resources
- **Common Targets:** REST APIs, web applications with predictable IDs (auto-increment integers)
- **Impact:** Unauthorized data access, PII exposure, account takeover potential
- **Attack Pattern:** Consecutive requests to same endpoint with varying ID parameters
- **Success Indicators:** HTTP 200 responses with different data (varying response sizes)
- **Mitigation:** Implement proper authorization checks, use indirect references (UUIDs), validate user permissions per request

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 5a, 5b can run in parallel (threat intel lookups)
- Critical path: 1 → 1b → 2 → 3 → 4 → 6 → 7 → 8 → Final Analysis
- Optional enrichment: 5a, 5b (threat intel)
