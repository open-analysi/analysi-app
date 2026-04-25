---
detection_rule: Passwd Found in Requested URL - Possible LFI Attack
alert_type: Web Attack
subcategory: LFI
source_category: WAF
mitre_tactics: [T1190, T1005]
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
      "time": "2026-04-26T10:10:00Z",
      "message": "Passwd Found in Requested URL - Possible LFI Attack",
      "finding_info": {
        "title": "Passwd Found in Requested URL - Possible LFI Attack",
        "desc": "URL Contains passwd",
        "uid": "0dc1451c-85ee-4ef6-b3cc-8caeb6e438dd",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "Passwd Found in Requested URL - Possible LFI Attack",
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
        "hostname": "WebServer1006",
        "name": "WebServer1006",
        "ip": "10.10.20.13"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "91.234.56.162"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://10.10.20.13/?file=../../../../etc/passwd"
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
          "src_endpoint": {"ip": "91.234.56.162"},
          "dst_endpoint": {"ip": "10.10.20.13"},
          "url": {"url_string": "https://10.10.20.13/?file=../../../../etc/passwd"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 1.1.4322)"
          }
        }
      ],
      "raw_data": "Rule : Passwd Found in Requested URL - Possible LFI Attack\nSeverity : High\nType : Web Attack\nEvent Time : March 1, 2022, 10:10 a.m.\nHostname : WebServer1006\nDestination IP Address : 10.10.20.13\nSource IP Address : 91.234.56.162\nHTTP Request Method : GET\nRequested URL : https://10.10.20.13/?file=../../../../etc/passwd\nUser-Agent :  Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; .NET CLR 1.1.4322)\nAlert Trigger Reason : URL Contains passwd\nDevice Action : Allowed",
      "unmapped": {
        "alert_trigger_reason": "URL Contains passwd",
        "log_source": "HTTP Firewall Logs"
      }
    }
---
# Passwd Found in Requested URL - Possible LFI Attack Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

![[common/by_source/waf-siem-evidence.md]]

![[common/by_type/lfi-analysis.md]]

![[common/evidence/threat-intel-enrichment.md]]

### 5. Attack Success Determination ★
- **Action:** Determine if LFI succeeded based on response patterns
- **Depends On:** Steps 2a, 2c, 3
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.lfi_payload_analysis, outputs.http_events
- **Decision Points:**
  - `status == 500 AND response_size == 0` → Unsuccessful (file path does not exist, example pattern)
  - `status == 200 AND response_size > 0` → Likely successful (file content returned)
  - `status == 403` → Blocked by WAF/application
  - `response contains file content markers (root:x:0:0)` → Definitive success
  - `all attempts have status 500` → No files accessible
  - `event_count > 50 in 30min` → Automated scanner behavior
  - `event_count < 10 AND targeted files` → Manual focused attack
- **Output:** lfi_attack_verdict

### 6. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 4a (optional), 5
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.lfi_attack_verdict, outputs.lfi_payload_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 7. Data Exposure Assessment
- **Action:** Determine if sensitive file contents were exposed
- **Depends On:** Steps 3, 5, 6
- **Pattern:** impact_assessment
- **Input:** outputs.lfi_payload_analysis, outputs.lfi_attack_verdict, outputs.response_patterns
- **Focus:** System file access (/etc/passwd, /etc/shadow), application config files, database credentials, API keys
- **Output:** lfi_exposure_assessment
- **Decision Points:**
  - `/etc/shadow accessed with status 200` → Password hashes compromised
  - `/etc/passwd accessed` → User enumeration successful
  - `Application config files` → Credentials/secrets potentially exposed
  - `No successful reads (all 500)` → No data exposed

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "LFI attack from ${get_src_ip(alert)} targeting ${get_primary_device(alert)} - [successful|unsuccessful] - [data exposed|no data exposed]"

## Conditional Logic

### Branch: Successful File Access
- **Condition:** outputs.lfi_attack_verdict.succeeded == true AND outputs.response_patterns.any_status == 200
- **Critical Actions:**
  - Immediate containment of affected host
  - Check for additional file access attempts
  - Audit what files were successfully read
  - Search for follow-up exploitation (RCE, privilege escalation)
  - Escalate to incident response team

### Branch: Unsuccessful Attack Pattern
- **Condition:** outputs.response_patterns.all_statuses == 500 AND outputs.response_patterns.all_sizes == 0
- **Fast Track:** True Positive (malicious intent) but unsuccessful - no files accessed
- **Actions:**
  - Block source IP at firewall
  - Review application security configuration
  - Monitor for follow-up attacks

### Branch: Automated Scanner Detected
- **Condition:** outputs.validated_hypothesis == "Automated LFI scanner" AND outputs.http_events.count > 50
- **Additional Steps:**
  - Verify if authorized security testing
  - Check scan schedule against detected time
  - If unauthorized, block source IP/ASN

### Branch: Credential Compromise
- **Condition:** outputs.lfi_exposure_assessment.shadow_accessed == true OR outputs.lfi_exposure_assessment.credentials_exposed == true
- **Critical Actions:**
  - Force password reset for ALL accounts
  - Rotate all application credentials
  - Audit all systems for lateral movement
  - Check for persistence mechanisms
  - Immediate escalation required

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR authorized_test_confirmed == true
- **Verification Steps:**
  - Check IT change management for scheduled penetration tests
  - Verify source IP matches known security vendor ranges
  - Contact security team to confirm authorization
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate for unauthorized testing

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for LFI pattern and success determination
2. **Response analysis:** Definitive indicator of successful file access (status 200 + content)
3. **Path pattern analysis:** Understanding attacker's target knowledge and sophistication
4. **Threat intelligence:** Context for attacker profile and risk assessment

### Common Patterns
- **Automated scanners:** High volume (50+ requests), multiple traversal depths, standard file targets
- **Manual testing:** Low volume (5-15 requests), focused on specific files, varied techniques
- **Successful LFI:** Status 200 with non-zero response size containing file content
- **Blocked LFI:** Status 500 (file not found), 403 (forbidden), or 0 bytes response

### Critical Indicators
- **High Priority:** /etc/shadow accessed (password hashes exposed)
- **Medium Priority:** /etc/passwd accessed (user enumeration), config files accessed (credentials)
- **Low Priority:** Non-existent file attempts only (reconnaissance, no access)

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 4a, 4b can run in parallel (threat intel lookups)
- Critical path: 1 → 2 → 3 → 5 → 6 → 8a → 8b
- Optional enrichment: 4a, 4b, 7

### Geo-Blocking Consideration
- If source IP is from unexpected geographic region and no business justification exists, consider geo-blocking as additional preventive measure
- Review security policies for geo-restriction implementation
