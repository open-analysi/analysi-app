---
detection_rule: Suspicious File Access with Code Execution Detected
alert_type: Web Attack
subcategory: Injection
source_category: WAF
mitre_tactics: [T1190, T1005, T1059]
integrations_required: [siem]
integrations_optional: [threat_intel, edr]
version: 1.0.0
last_updated: 2025-11-17
author: runbook-matcher
source: composed
provenance:
  composition_sources:
    - passwd-found-in-url-lfi-attack.md (LFI pattern analysis)
    - command-injection-detection.md (RCE verification pattern)
  base_template: web-attack-pattern
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
      "severity_id": 5,
      "severity": "Critical",
      "status_id": 1,
      "status": "New",
      "time": "2024-01-18T09:47:00Z",
      "message": "Suspicious File Access with Code Execution Detected",
      "finding_info": {
        "title": "Suspicious File Access with Code Execution Detected",
        "uid": "2a5cc3d0-717d-4562-b048-87e79b9c9f04",
        "types": [
          "Web Attack",
          "Injection"
        ],
        "analytic": {
          "name": "Suspicious File Access with Code Execution Detected",
          "type_id": 1,
          "type": "Rule"
        },
        "attacks": [
          {
            "technique": {
              "uid": "T1190",
              "name": "Exploit Public-Facing Application"
            },
            "tactic": {
              "uid": "TA0001",
              "name": "Initial Access"
            }
          },
          {
            "technique": {
              "uid": "T1005",
              "name": "Data from Local System"
            },
            "tactic": {
              "uid": "TA0009",
              "name": "Collection"
            }
          },
          {
            "technique": {
              "uid": "T1059",
              "name": "Command and Scripting Interpreter"
            },
            "tactic": {
              "uid": "TA0002",
              "name": "Execution"
            }
          }
        ],
        "desc": "Web application received requests attempting to access system log files through directory traversal. User-Agent header contains PHP code suggesting log poisoning attack. Subsequent request attempts to include the poisoned log file for code execution. Attack shows characteristics of file inclusion being used as a vector for remote code execution."
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
        "hostname": "WebApp-Prod-03",
        "name": "WebApp-Prod-03"
      },
      "evidences": [
        {
          "src_endpoint": {"ip": "91.198.174.192"},
          "dst_endpoint": {"ip": "172.16.20.54"},
          "url": {"url_string": "/app/download?file=../../../../var/log/apache2/access.log&c=whoami"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "<?php system($_GET['c']); ?>"
          }
        }
      ],
      "raw_data": "{\"initial_requests\": [{\"request_url\": \"/app/download?file=../../../../var/log/apache2/access.log\", \"http_method\": \"GET\", \"user_agent\": \"<?php system($_GET['c']); ?>\", \"src_ip\": \"91.198.174.192\", \"response_status\": 200, \"response_size\": 45821, \"timestamp\": \"2024-01-18T09:45:12Z\"}, {\"request_url\": \"/app/download?file=../../../var/log/apache2/error.log\", \"http_method\": \"GET\", \"user_agent\": \"<?php system($_GET['c']); ?>\", \"src_ip\": \"91.198.174.192\", \"response_status\": 200, \"response_size\": 12493, \"timestamp\": \"2024-01-18T09:45:43Z\"}], \"exploitation_request\": {\"request_url\": \"/app/download?file=../../../../var/log/apache2/access.log&c=whoami\", \"http_method\": \"GET\", \"user_agent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\", \"src_ip\": \"91.198.174.192\", \"response_status\": 200, \"response_size\": 46102, \"timestamp\": \"2024-01-18T09:47:22Z\"}, \"command_execution_indicators\": {\"response_contains_command_output\": true, \"observed_commands\": [\"whoami\", \"id\", \"uname -a\"], \"response_size_variance\": \"significant\"}, \"src_ip\": \"91.198.174.192\", \"dest_ip\": \"172.16.20.54\", \"hostname\": \"WebApp-Prod-03\", \"destination_port\": 443}"
    }
---
# Suspicious File Access with Code Execution Detected Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

![[common/by_source/waf-siem-evidence.md]]

### 2b. Log Poisoning Pattern Analysis ★
- **Action:** Extract log file access attempts and analyze for code injection in headers
- **Purpose:** Validates: "Log poisoning attack" vs "Benign log file access"
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Log file paths (access.log, error.log), code patterns in User-Agent/headers (<?php, <?=, eval), directory traversal sequences
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** log_poisoning_attempts
- **Decision Points:**
  - Code in User-Agent + log file access → Log poisoning
  - Multiple log file attempts → Testing which logs are accessible
  - Standard User-Agent + log access → Benign or reconnaissance

### 3. Payload Analysis ★
- **Action:** Decode and analyze injection payloads and file paths
- **Depends On:** Step 2b
- **Pattern:** payload_analysis
- **Input:** outputs.log_poisoning_attempts.user_agent, outputs.log_poisoning_attempts.uri_query
- **Focus:** Injection language (PHP, JSP, ASP), payload sophistication (system(), exec(), eval()), command parameters, traversal depth, target log files
- **Output:** payload_analysis
- **Decision Points:**
  - Simple system() call → Basic RCE payload
  - Obfuscated/encoded payload → Sophisticated attacker
  - Multiple log files tested → Probing for accessible logs
  - Web shell functions → Persistent access attempt

### 4. Code Execution Evidence Collection ★
- **Action:** Search for evidence of successful code execution via poisoned logs
- **Depends On:** Steps 2b, 3
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Requests to same log file with command parameters, response size variance indicating command output, command parameters in URLs (c=whoami, cmd=id)
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** execution_evidence
- **Decision Points:**
  - Log access → Log access with cmd parameter → RCE chain
  - Response sizes vary significantly → Different command outputs
  - No follow-up requests → Poisoning only, no execution attempt

![[common/evidence/threat-intel-enrichment.md]]

### 6. Attack Success Determination ★
- **Action:** Determine if log poisoning succeeded and code was executed
- **Depends On:** Steps 2c, 3, 4
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.payload_analysis, outputs.execution_evidence
- **Decision Points:**
  - `status == 200 AND response_size > 0 on log access` → Log file accessible
  - `status == 200 on execution attempt AND response_size varies` → Code likely executed
  - `execution_evidence shows command parameters` → RCE attempted
  - `response contains command output indicators (uid=, gid=)` → Definitive execution
  - `all log access attempts status 403/404` → Logs not accessible
  - `log accessible but no execution attempts` → Poisoning only
- **Output:** attack_verdict

### 7. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 5a (optional), 6
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.attack_verdict, outputs.payload_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 8. System Compromise Assessment
- **Action:** Determine scope of compromise if RCE succeeded
- **Depends On:** Steps 3, 4, 6, 7
- **Pattern:** impact_assessment
- **Input:** outputs.payload_analysis, outputs.execution_evidence, outputs.attack_verdict
- **Focus:** Commands executed (whoami, id, uname vs cat /etc/shadow), privilege level indicators, sensitive file access attempts, persistence mechanism installation
- **Output:** compromise_assessment
- **Decision Points:**
  - `commands include /etc/shadow, /etc/passwd` → Credential theft attempt
  - `commands include wget, curl with external IPs` → Payload download attempt
  - `reconnaissance commands only (whoami, id)` → Initial phase
  - `web shell installation indicators` → Persistent access established

### 9. EDR Verification
- **Action:** Cross-reference with endpoint data if EDR available
- **Depends On:** Steps 6, 8
- **Pattern:** integration_query
- **Integration:** edr
- **Condition:** IF outputs.attack_verdict.succeeded == true
- **Focus:** Process execution history matching observed commands, web server process child processes, file system changes
- **Fields:** get_primary_device(alert), get_dst_ip(alert)
- **Output:** endpoint_verification
- **Parallel:** No

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "Log poisoning RCE from ${get_src_ip(alert)} targeting ${get_primary_device(alert)} - [successful|unsuccessful] - [code executed|poisoning only]"

## Conditional Logic

### Branch: Successful RCE
- **Condition:** outputs.attack_verdict.succeeded == true AND outputs.execution_evidence.command_execution_confirmed == true
- **Critical Actions:**
  - Immediate containment of affected host
  - Kill web server process if still running malicious code
  - Search for web shells or persistence mechanisms
  - Audit all file system changes since attack time
  - Check for lateral movement attempts
  - Review all commands executed for data exfiltration
  - Escalate to incident response team immediately

### Branch: Log Poisoning Only (No Execution)
- **Condition:** outputs.log_poisoning_attempts.found == true BUT outputs.execution_evidence.command_execution_confirmed == false
- **Assessment:** Attacker poisoned logs but didn't execute or execution failed
- **Actions:**
  - Clear/rotate affected log files
  - Block source IP at firewall
  - Verify application doesn't include/eval log files
  - Monitor for follow-up execution attempts

### Branch: Unsuccessful Attack (Logs Not Accessible)
- **Condition:** outputs.response_patterns.all_statuses == 403|404
- **Fast Track:** True Positive (malicious intent) but unsuccessful - logs protected
- **Actions:**
  - Block source IP at firewall
  - Document attack pattern
  - Monitor for alternative attack vectors

### Branch: Credential Compromise
- **Condition:** outputs.compromise_assessment.credentials_accessed == true
- **Critical Actions:**
  - Force password reset for ALL accounts
  - Rotate all application credentials and API keys
  - Audit all systems for lateral movement
  - Check for privilege escalation
  - Immediate escalation required

### Branch: Web Shell Installed
- **Condition:** outputs.compromise_assessment.webshell_indicators == true OR outputs.endpoint_verification.suspicious_files_created == true
- **Critical Actions:**
  - Locate and remove web shell files
  - Full forensic analysis of affected host
  - Check for backdoor accounts
  - Review all web-accessible directories for malicious files
  - Consider full host rebuild

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner"
- **Verification Steps:**
  - Check IT change management for scheduled penetration tests
  - Verify source IP matches known security vendor ranges
  - Contact security team to confirm authorization
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate for unauthorized testing

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for log poisoning pattern and RCE attempts
2. **Response size variance:** Strong indicator of command execution (different outputs)
3. **Payload analysis:** Understanding injection technique and target logs
4. **EDR data:** Definitive proof of code execution on endpoint (if available)

### Attack Progression Pattern
1. **Reconnaissance:** Test which log files are accessible (access.log, error.log)
2. **Poisoning:** Inject code payload into User-Agent header to poison logs
3. **Verification:** Access log file to verify code was written
4. **Exploitation:** Access log file with command parameter to execute code
5. **Post-Exploitation:** Execute commands for reconnaissance, credential theft, or persistence

### Common Patterns
- **Successful log poisoning + RCE:** Code in User-Agent → log access (200) → log access with cmd param (200, varying sizes)
- **Poisoning only:** Code in User-Agent → log access (200) → no follow-up execution attempts
- **Blocked attack:** Log access attempts return 403/404 → logs not accessible
- **Sophisticated attacker:** Obfuscated payloads, multiple injection points, immediate persistence attempts

### Critical Indicators
- **Critical:** RCE confirmed with credential access or web shell installation
- **High Priority:** RCE confirmed with reconnaissance commands
- **Medium Priority:** Log poisoning successful but no execution
- **Low Priority:** Log poisoning attempted but logs not accessible

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 5a, 5b can run in parallel (threat intel lookups)
- Step 9 (EDR) only runs if attack succeeded (conditional)
- Critical path: 1 → 2b → 3 → 4 → 6 → 7 → 8 → 10a → 10b
- Optional enrichment: 5a, 5b, 9

### Notable Gap
- This runbook composed from LFI and command injection patterns
- No existing runbook specifically covered log poisoning technique
- EDR verification step is optional (not all WAF alerts will have EDR context)
