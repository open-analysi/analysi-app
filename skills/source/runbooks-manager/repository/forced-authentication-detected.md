---
detection_rule: Forced Authentication Detected
alert_type: Brute Force
subcategory: Authentication Attack
source_category: WAF
mitre_tactics: [T1110, T1078]
integrations_required: [siem]
integrations_optional: [threat_intel, edr, email]
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
      "severity_id": 3,
      "severity": "Medium",
      "status_id": 1,
      "status": "New",
      "time": "2026-04-26T14:15:00Z",
      "message": "Forced Authentication Detected",
      "finding_info": {
        "title": "Forced Authentication Detected",
        "uid": "087635ad-04ea-4b29-b49d-22a850ac6430",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "Forced Authentication Detected",
          "type_id": 1,
          "type": "Rule"
        },
        "desc": "Multiple POST requests were soon seen from the same IP to the fixed URI \"/accounts/login\"."
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
      "action_id": 1,
      "action": "Allowed",
      "device": {
        "hostname": "WebServer_Test",
        "name": "WebServer_Test"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "91.234.56.175"
        },
        {
          "name": "dest_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "203.198.7.61"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "http://test-frontend.example.com/accounts/login"
        }
      ],
      "raw_data": "Rule : Forced Authentication Detected\t\nSeverity : Medium\nType : Web Attack\nEvent Time : Dec, 12, 2023, 02:15 PM\nSource IP : 91.234.56.175\nDestination IP : 203.198.7.61\nHost : WebServer_Test\nRequest URL : http://test-frontend.example.com/accounts/login\nRequest Method : POST\nDevice Action : Permitted\nAlert Trigger Reason : Multiple POST requests were soon seen from the same IP to the fixed URI \"/accounts/login\".",
      "evidences": [
        {
          "src_endpoint": {"ip": "91.234.56.175"},
          "dst_endpoint": {"ip": "203.198.7.61"},
          "url": {"url_string": "http://test-frontend.example.com/accounts/login"},
          "http_request": {
            "http_method": "POST",
            "user_agent": ""
          }
        }
      ],
      "unmapped": {
        "alert_trigger_reason": "Multiple POST requests were soon seen from the same IP to the fixed URI \"/accounts/login\"."
      }
    }
---
# Forced Authentication Detected Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

### 2. Source IP Reconnaissance Analysis ★
- **Action:** Check for port scanning activity preceding authentication attempts
- **Purpose:** Validates: "Random login attempt" vs "Reconnaissance followed by targeted attack"
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Firewall logs showing connection attempts across multiple ports (FTP, SMTP, DNS, HTTP, POP3, HTTPS, RDP)
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** port_scan_activity
- **Decision Points:**
  - `single_port_activity` → Direct targeted attack
  - `multiple_ports_scanned (5+ ports)` → Reconnaissance phase detected
  - `rejected_connections` → Attack mitigation in progress

### Supporting Evidence Collection ★
- **Purpose:** Collect SIEM data to determine attack scope and success
- **Parallel:** Yes

#### 3a. Authentication Attempt Enumeration ★
- **Action:** Retrieve all POST requests to login endpoint from source IP
- **Purpose:** Validates attack pattern and identifies credential pairs attempted
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** HTTP POST requests to login URIs, extract username/password combinations
- **Fields:** get_src_ip(alert), get_url(alert)
- **Output:** login_attempts
- **Decision Points:**
  - `attempt_count < 10` → Low-volume targeted attack
  - `attempt_count 10-50` → Moderate brute force
  - `attempt_count > 50` → High-volume automated attack
  - `credential_diversity` → Dictionary attack vs credential stuffing

#### 3b. OS Authentication Logs ★
- **Action:** Query OS logs for successful authentication events from source IP
- **Purpose:** Validates attack success - critical for escalation decision
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Successful login events, user accounts compromised, timing correlation
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** authentication_results
- **Decision Points:**
  - `successful_login == true` → Attack succeeded (CRITICAL - escalate)
  - `successful_login == false AND all_rejected` → Attack blocked
  - `username identified` → Specific account compromised

![[common/evidence/threat-intel-enrichment.md]]

### 5. Credential Weakness Assessment
- **Action:** Analyze attempted credentials for common weak patterns
- **Depends On:** Step 3a
- **Pattern:** payload_analysis
- **Input:** outputs.login_attempts.credentials
- **Focus:** Identify credential patterns (admin/12345, root/123456), assess if default credentials, check credential strength
- **Output:** credential_analysis
- **Decision Points:**
  - `default_credentials detected` → Severe security risk
  - `weak_passwords (< 8 chars, no complexity)` → Password policy violation
  - `common_credentials (admin, root, test)` → High-risk accounts targeted

### 6. Planned Test Verification ★
- **Action:** Check for authorized penetration testing or security assessments
- **Purpose:** Validates: "Malicious attack" vs "Authorized security testing"
- **Pattern:** integration_query
- **Integration:** email
- **Condition:** IF email integration configured
- **Fields:** get_src_ip(alert), get_url(alert), get_primary_device(alert)
- **Output:** planned_test_check
- **Decision Points:**
  - `authorized_test == true` → Benign (mark as expected)
  - `authorized_test == false` → Malicious attack (proceed with escalation)

### 7. EDR Endpoint Validation
- **Action:** Check EDR for post-authentication activity on compromised system
- **Depends On:** Step 3b
- **Condition:** IF outputs.authentication_results.successful_login == true AND edr configured
- **Pattern:** integration_query
- **Integration:** edr
- **Focus:** Command execution, lateral movement, persistence mechanisms
- **Fields:** get_primary_device(alert), get_dst_ip(alert)
- **Output:** edr_activity

### 8. Attack Success Determination ★
- **Action:** Determine if brute force succeeded and assess impact
- **Depends On:** Steps 3a, 3b, 5
- **Pattern:** impact_assessment
- **Input:** outputs.login_attempts, outputs.authentication_results, outputs.credential_analysis, outputs.port_scan_activity (optional), outputs.edr_activity (optional)
- **Decision Points:**
  - `successful_login AND weak_credentials` → Successful brute force with critical security gap
  - `successful_login AND reconnaissance` → Sophisticated multi-stage attack
  - `no_successful_login AND high_attempt_count` → Blocked attack, monitor for persistence
  - `test_environment AND successful_login` → Potential honeypot (verify server purpose)
- **Output:** attack_verdict

### 9. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 2, 3a, 3b, 4a (optional), 6, 8
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.attack_verdict, outputs.port_scan_activity, outputs.ip_reputation (if available), outputs.planned_test_check
- **Output:** validated_hypothesis

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "Brute force from ${get_src_ip(alert)} - [successful|unsuccessful] - [account compromised: ${username}|blocked]"

## Conditional Logic

### Branch: Successful Authentication
- **Condition:** outputs.authentication_results.successful_login == true
- **Additional Steps:**
  - Immediate escalation to Tier 2 incident response
  - Identify compromised user account
  - Check for lateral movement indicators
  - Search for persistence mechanisms
  - Review account activity post-compromise
  - Consider password reset and account suspension
  - Assess if production vs test environment

### Branch: Blocked Attack
- **Condition:** outputs.authentication_results.successful_login == false AND outputs.login_attempts.count < 50
- **Fast Track:** True Positive but unsuccessful - attacker blocked, document for tracking but lower priority

### Branch: High-Volume Automated Attack
- **Condition:** outputs.login_attempts.count > 50
- **Additional Steps:**
  - Classify as automated brute force tool
  - Check for distributed attack sources (multiple IPs)
  - Review firewall rules for rate limiting
  - Consider IP blocking or CAPTCHA implementation
  - Assess application-level protections

### Branch: Reconnaissance Detected
- **Condition:** outputs.port_scan_activity.scanned_ports > 5
- **Additional Steps:**
  - Classify as multi-stage attack (recon + exploitation)
  - Higher sophistication indicator
  - Check for scanning activity against other hosts
  - Review network segmentation effectiveness
  - Elevated threat actor assessment

### Branch: Authorized Security Testing
- **Condition:** outputs.planned_test_check.authorized == true
- **Verification Steps:**
  - Verify testing window matches alert time
  - Confirm source IP matches approved vendor
  - If authorized → Mark as Benign with reference to approval
  - If timing/source mismatch → Escalate for unauthorized testing

### Branch: Weak Credential Compromise
- **Condition:** outputs.authentication_results.successful_login == true AND outputs.credential_analysis.weak_credentials == true
- **Additional Steps:**
  - Critical security policy violation
  - Immediate password policy review required
  - Assess scope of weak credentials across environment
  - Force password reset organization-wide if systemic issue
  - Consider MFA implementation urgency

### Branch: Test Environment Compromise
- **Condition:** outputs.authentication_results.successful_login == true AND get_primary_device(alert) contains "test|dev|staging"
- **Verification Steps:**
  - Verify server purpose (production vs honeypot vs test)
  - If honeypot → Lower severity, analyze attacker TTPs
  - If test environment → Assess production impact risk
  - Check for sensitive data in test environment
  - Lower escalation priority but still document

## Investigation Notes

### Key Evidence Sources
1. **Firewall/Proxy logs:** Port scanning reconnaissance patterns
2. **HTTP logs:** Authentication attempt enumeration and credential analysis
3. **OS authentication logs:** Definitive attack success indicator (CRITICAL)
4. **Threat intelligence:** Attacker attribution and risk context
5. **EDR (if available):** Post-compromise activity detection

### Common Patterns
- **Reconnaissance + Brute Force:** Port scan followed by targeted login attempts (sophisticated)
- **Direct Brute Force:** Immediate login attempts without scanning (automated tool)
- **Low-volume targeted:** < 10 attempts with specific credentials (credential stuffing)
- **High-volume automated:** 50+ attempts with dictionary (brute force tool)
- **Successful compromise indicators:** OS logs showing "User Login Successful" from source IP

### Investigation Efficiency
- Steps 3a, 3b can run in parallel (SIEM queries)
- Steps 4a, 4b can run in parallel (threat intel lookups)
- Step 6 (planned test check) can run in parallel with Step 5
- Critical path: 1 → 2 → 3a,3b → 8 → 9 → Final Analysis
- Optional enrichment: 4a, 4b, 5, 6, 7

### Critical Decision: Escalation Required
- **ALWAYS escalate if:** outputs.authentication_results.successful_login == true
- **Monitor if:** High attempt count but no successful login
- **Lower priority if:** Test environment OR authorized testing OR blocked with low attempt count

### Security Recommendations
- Implement MFA for all authentication endpoints
- Enforce strong password policies
- Deploy rate limiting on login endpoints
- Use HTTPS instead of HTTP for authentication
- Consider account lockout after N failed attempts
- Monitor for credential spraying across multiple accounts
