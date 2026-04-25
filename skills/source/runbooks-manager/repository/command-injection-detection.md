---
detection_rule: Whoami Command Detected in Request Body
alert_type: Web Attack
subcategory: Command Injection
source_category: WAF
mitre_tactics: [T1190, T1059]
integrations_required: [siem, edr]
integrations_optional: [threat_intel]
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
      "time": "2026-04-26T04:12:00Z",
      "message": "Whoami Command Detected in Request Body",
      "finding_info": {
        "title": "Whoami Command Detected in Request Body",
        "desc": "Request Body Contains whoami string",
        "uid": "4e9adbb0-f108-4ac2-98cd-e5d6a5edac60",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "Whoami Command Detected in Request Body",
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
        "hostname": "WebServer1004",
        "name": "WebServer1004",
        "ip": "10.10.20.16"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "91.234.56.87"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://10.10.20.16/video/"
        },
        {
          "name": "user_agent",
          "type_id": 16,
          "type": "HTTP User-Agent",
          "value": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)"
        }
      ],
      "evidences": [
        {
          "src_endpoint": {"ip": "91.234.56.87"},
          "dst_endpoint": {"ip": "10.10.20.16"},
          "url": {"url_string": "https://10.10.20.16/video/"},
          "http_request": {
            "http_method": "POST",
            "user_agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)"
          }
        }
      ],
      "raw_data": "Rule : Whoami Command Detected in Request Body\nSeverity : High\nType : Web Attack\nEvent Time: Feb. 28, 2022, 4:12 a.m.\nHostname : WebServer1004\nDestination IP Address : 10.10.20.16\nSource IP Address : 91.234.56.87\nHTTP Request Method : POST\nRequested URL : https://10.10.20.16/video/\nUser-Agent : Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)\nAlert Trigger Reason : Request Body Contains whoami string\nDevice Action : Allowed",
      "unmapped": {
        "alert_trigger_reason": "Request Body Contains whoami string",
        "log_source": "HTTP Firewall Logs"
      }
    }
---
# Whoami Command Detected in Request Body Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

![[common/by_source/waf-siem-evidence.md]]

![[common/by_type/command-injection-analysis.md]]

![[common/evidence/threat-intel-enrichment.md]]

### 6. Attack Success Determination ★
- **Action:** Determine if command injection succeeded and assess compromise level
- **Depends On:** Steps 2c, 3, 4
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.cmdi_payload_analysis, outputs.cmdi_execution_evidence
- **Decision Points:**
  - `all statuses == 200 AND endpoint_history shows commands` → Successful execution confirmed
  - `response_sizes vary significantly` → Commands returned different output (example: 912 bytes for whoami, 1321 bytes for /etc/passwd)
  - `endpoint_history shows /etc/shadow access` → Credentials compromised
  - `all statuses == 403|500` → Injection blocked at application/WAF level
  - `status 200 BUT no endpoint_history` → WAF allowed but application blocked
  - `sensitive files accessed (passwd, shadow)` → Critical compromise
- **Output:** cmdi_attack_verdict

### 7. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 5a (optional), 6
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.cmdi_attack_verdict, outputs.cmdi_payload_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 8. Credential Compromise Assessment
- **Action:** Determine if sensitive credential files were accessed
- **Depends On:** Steps 3, 4, 6
- **Pattern:** impact_assessment
- **Input:** outputs.cmdi_payload_analysis, outputs.cmdi_execution_evidence, outputs.cmdi_attack_verdict
- **Focus:** Access to /etc/passwd (usernames), /etc/shadow (password hashes), privilege level of executed commands (root vs user)
- **Output:** cmdi_credential_impact
- **Decision Points:**
  - `/etc/shadow accessed with status 200` → Hashed passwords compromised, immediate password reset required
  - `/etc/passwd only` → Usernames exposed but not passwords
  - `Commands executed as root` → Full system compromise
  - `Commands executed as web user` → Limited compromise

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "Command injection from ${get_src_ip(alert)} - [successful|unsuccessful] - [credentials compromised|no data exposed]"

## Conditional Logic

### Branch: Successful Credential Compromise
- **Condition:** outputs.cmdi_attack_verdict.succeeded == true AND outputs.cmdi_credential_impact.shadow_accessed == true
- **Critical Actions:**
  - Immediate containment of affected host
  - Force password reset for ALL accounts
  - Audit all systems for lateral movement
  - Check for persistence mechanisms
  - Escalate to incident response team

### Branch: Failed Injection Attempt
- **Condition:** outputs.response_patterns.all_statuses != 200 OR outputs.cmdi_execution_evidence == null
- **Fast Track:** True Positive (malicious intent) but unsuccessful
- **Actions:**
  - Block source IP at firewall
  - Review application security
  - Monitor for follow-up attacks

### Branch: Blocked at Application Level
- **Condition:** outputs.response_patterns.all_statuses == 200 BUT outputs.cmdi_execution_evidence == null
- **Assessment:** WAF detected but application prevented execution
- **Disposition:** True Positive (malicious intent) but unsuccessful attack

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR outputs.geo_abuse_data.abuse_reports == 0
- **Verification Steps:**
  - Check IT change management for scheduled penetration tests
  - Verify source IP matches known security vendor ranges
  - Contact security team to confirm authorization
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate for unauthorized testing

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for command injection pattern and response analysis
2. **EDR command history:** Definitive proof of successful execution on endpoint
3. **Payload decoding:** Critical for understanding injected commands and attack progression
4. **Response patterns:** Indicator of command output (varying sizes = different command results)

### Common Patterns
- **Successful injection:** Status 200 + varying response sizes + endpoint command history matches
- **Blocked injection:** Status 403/500 OR status 200 with no endpoint evidence
- **Credential theft:** Sequential progression: whoami → ls → uname → cat /etc/passwd → cat /etc/shadow
- **Reconnaissance phase:** System info gathering only (whoami, uname, ls) without sensitive file access

### Critical Indicators
- **High Priority:** /etc/shadow accessed (hashed passwords compromised)
- **Medium Priority:** /etc/passwd accessed (username enumeration)
- **Low Priority:** System info only (reconnaissance, no data theft)

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 4 and 5a, 5b can run in parallel (EDR + threat intel lookups)
- Critical path: 1 → 2 → 3 → 4 → 6 → 7 → 8 → 9a → 9b
- Optional enrichment: 5a, 5b
