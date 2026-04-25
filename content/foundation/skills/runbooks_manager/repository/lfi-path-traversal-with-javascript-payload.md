---
detection_rule: LFI Path Traversal with Embedded Javascript Payload Detected
alert_type: Web Attack
subcategory: Injection
source_category: WAF
mitre_tactics: [T1190, T1005, T1189, T1059]
integrations_required: [siem]
integrations_optional: [threat_intel, edr]
version: 1.0.0
author: runbook-match-agent
source: composed
provenance:
  - passwd-found-in-url-lfi-attack.md (LFI path traversal analysis and attack success determination)
  - xss-detection.md (JavaScript/XSS payload analysis and impact assessment)
  - sql-injection-with-stored-xss-payload.md (compound injection composition structure)
  - log-poisoning-rce-detection.md (multi-technique compound attack investigation flow)
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
      "time": "2026-04-26T14:22:00Z",
      "message": "LFI Path Traversal with Embedded Javascript Payload Detected",
      "finding_info": {
        "title": "LFI Path Traversal with Embedded Javascript Payload Detected",
        "desc": "Path traversal sequence with embedded JavaScript detected in requested URL",
        "uid": "example-uid",
        "types": ["Web Attack"],
        "analytic": {
          "name": "LFI Path Traversal with Embedded Javascript Payload Detected",
          "type_id": 1,
          "type": "Rule"
        },
        "attacks": [
          {"technique": {"uid": "T1190", "name": "Exploit Public-Facing Application"}},
          {"technique": {"uid": "T1005", "name": "Data from Local System"}},
          {"technique": {"uid": "T1189", "name": "Drive-by Compromise"}},
          {"technique": {"uid": "T1059", "name": "Command and Scripting Interpreter"}}
        ]
      },
      "metadata": {
        "version": "1.8.0",
        "product": {"name": "HTTP Parsing Firewall", "vendor_name": "Firewall"},
        "labels": ["source_category:WAF"]
      },
      "device": {
        "hostname": "WebServer1010",
        "name": "WebServer1010",
        "ip": "10.10.20.20"
      },
      "evidences": [
        {
          "src_endpoint": {"ip": "203.0.113.50"},
          "dst_endpoint": {"ip": "10.10.20.20"},
          "url": {"url_string": "https://10.10.20.20/page?file=../../../../etc/passwd%00<script>alert(1)</script>"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          }
        }
      ]
    }
---
# LFI Path Traversal with Embedded Javascript Payload Investigation Runbook

## Overview

This runbook investigates WAF alerts detecting a compound attack combining Local File Inclusion (LFI) path traversal sequences with embedded JavaScript payloads in the same request. The attacker may be attempting:

1. **LFI for file disclosure** - Read sensitive files via directory traversal (e.g., /etc/passwd)
2. **XSS/JS injection** - Embed JavaScript for client-side execution (stored XSS, log poisoning, template injection)
3. **Chained exploitation** - Use LFI to include a log file poisoned with the JS payload (log poisoning RCE variant)
4. **Automated scanning** - A fuzzer probing multiple injection techniques simultaneously

The compound nature of this alert requires investigating both vectors independently before determining whether they represent a coordinated chain or two independent probes.

## Steps

### 1. Alert Understanding & Initial Assessment ★
- **Action:** Analyze alert and form investigation hypotheses
- **Pattern:** hypothesis_formation
- **Input:** finding_info.title, severity, get_src_ip(alert), get_dst_ip(alert), get_url(alert), get_http_method(alert), get_user_agent(alert), finding_info.desc
- **Outputs:**
  - context_summary: Human-readable alert summary
  - investigation_hypotheses: List of theories to investigate
  - key_observables: Key indicators from the alert
- **Focus:** Identify whether path traversal and JavaScript appear in same parameter vs separate parameters, URL vs body vs headers

### Supporting Evidence Collection ★
- **Purpose:** Collect SIEM data to validate hypotheses and identify full attack scope
- **Parallel:** Yes

#### 2a. SIEM Event Retrieval ★
- **Action:** Retrieve all HTTP requests from attacker IP to identify attack pattern and scope
- **Purpose:** Validates attack progression, scope, and whether this is one-off vs campaign
- **Pattern:** integration_query
- **Integration:** siem
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** http_events

#### 2b. Response Pattern Analysis ★
- **Action:** Analyze HTTP response patterns to detect successful exploitation
- **Purpose:** Validates attack success vs failure for both LFI and JS components
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Response sizes, status codes, patterns indicating exploitation success
- **Fields:** get_src_ip(alert)
- **Output:** response_patterns

### 3. LFI Payload & Path Traversal Analysis ★
- **Action:** Extract file inclusion attempts and analyze traversal patterns
- **Purpose:** Validates: "Automated scanning" vs "Targeted file access" - determines which files the attacker was trying to read
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Directory traversal sequences (../, ../../), sensitive file targets (/etc/passwd, /etc/shadow, config files), traversal depth, URL encoding techniques, path manipulation methods, parameter usage patterns
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** lfi_payload_analysis
- **Decision Points:**
  - Single file path → Manual testing
  - Multiple traversal depths → Probing for correct path
  - Multiple target files → Automated scanner
  - System files only (/etc/passwd) → Reconnaissance
  - Application config files → Targeted exploitation
  - Log file targets (access.log, error.log) → Possible log poisoning chain

### 4. JavaScript Payload Analysis ★
- **Action:** Extract JavaScript injection attempts, URL decode payloads, and identify injection techniques
- **Purpose:** Validates: "XSS probe" vs "Log poisoning attempt" vs "Template injection" - determines the JS component's intent
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** JavaScript patterns in URLs and parameters (script tags, event handlers, javascript: protocol, SVG vectors), presence of JS in User-Agent header (log poisoning indicator), URL encoding (%3C, %3E, %22), payload location (URL param vs header vs body), sophistication and attack progression
- **Fields:** get_src_ip(alert)
- **Output:** js_payload_analysis
- **Decision Points:**
  - JS in URL parameter + path traversal in URL → Stored XSS or polyglot probe
  - JS in User-Agent header + path traversal to log files → Log poisoning chain (see log-poisoning-rce-detection.md)
  - Single JS payload variation → Manual testing
  - Multiple payload types in sequence → Automated scanner/fuzzer
  - Obfuscated/encoded patterns → Advanced evasion attempts
  - Classic patterns (alert(), prompt()) → Basic XSS testing
  - JS accessing file system (fetch('/etc/passwd')) → Chained exploitation attempt

### 5. Attack Chain Assessment ★
- **Action:** Determine if LFI and JavaScript components are coordinated or independent
- **Depends On:** Steps 3, 4
- **Pattern:** payload_analysis
- **Input:** outputs.lfi_payload_analysis, outputs.js_payload_analysis, outputs.http_events
- **Focus:** Temporal correlation between LFI and JS requests, same vs different parameters, whether JS is in User-Agent during log file traversal, whether payloads reference each other
- **Output:** chain_assessment
- **Decision Points:**
  - JS in User-Agent + log file in path traversal → Log poisoning RCE chain (HIGH severity)
  - Path traversal + JS in same URL parameter → Polyglot or combined probe
  - Path traversal and JS in entirely separate requests → Independent techniques from same source
  - JS references a local file path → LFI-to-XSS chained exploit attempt
  - No temporal correlation → Automated fuzzer hitting multiple payloads

### Threat Intelligence Enrichment
- **Parallel:** Yes
- **Optional:** Both sources can fail gracefully

#### 6a. IP Reputation Check
- **Action:** Check attacker IP reputation in threat intelligence sources
- **Purpose:** Validates threat actor profile and attribution
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** ip_reputation

#### 6b. IP Abuse History & Geolocation
- **Action:** Check IP abuse history and geographic location from threat databases
- **Purpose:** Context for attacker origin and history
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** geo_abuse_data

### 7. LFI Attack Success Determination ★
- **Action:** Determine if LFI file access succeeded based on response patterns
- **Depends On:** Steps 2a, 2b, 3, 5
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.lfi_payload_analysis, outputs.http_events
- **Decision Points:**
  - `status == 200 AND response_size > 0` → Likely successful file access (content returned)
  - `response contains file content markers (root:x:0:0)` → Definitive LFI success
  - `status == 500 AND response_size == 0` → Unsuccessful (file path does not exist)
  - `status == 403` → Blocked by WAF/application
  - `all attempts have status 500` → No files accessible
  - `event_count > 50 in 30min` → Automated scanner behavior
  - `event_count < 10 AND targeted files` → Manual focused attack
- **Output:** lfi_verdict

### 8. JavaScript Execution Success Determination ★
- **Action:** Determine if JavaScript payload was reflected or executed
- **Depends On:** Steps 2b, 4, 5
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.js_payload_analysis, outputs.chain_assessment
- **Decision Points:**
  - `status == 200 AND response_size > 0 AND payload reflected in response` → XSS injection succeeded
  - `status == 302 AND response_size == 0` → Redirected before execution
  - `status == 403/blocked` → WAF blocked JS payload
  - `JS in User-Agent + log access 200` → Log poisoned (code may execute on next log inclusion)
  - `No reflected payload in response body` → JS blocked or not reflected
- **Output:** js_verdict

### 9. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses considering both LFI and JS components
- **Depends On:** Steps 1, 3, 4, 5, 7, 8
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.lfi_verdict, outputs.js_verdict, outputs.chain_assessment, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 10. Data Exposure Assessment
- **Action:** Determine if sensitive file contents were exposed via LFI
- **Depends On:** Steps 3, 7, 9
- **Pattern:** impact_assessment
- **Input:** outputs.lfi_payload_analysis, outputs.lfi_verdict, outputs.response_patterns
- **Focus:** System file access (/etc/passwd, /etc/shadow), application config files, database credentials, API keys, log files (which could contain previously injected code)
- **Output:** lfi_exposure_assessment
- **Decision Points:**
  - `/etc/shadow accessed with status 200` → Password hashes compromised
  - `/etc/passwd accessed` → User enumeration successful
  - `Application config files` → Credentials/secrets potentially exposed
  - `Log files accessed` → May expose previously injected payloads or sensitive log data
  - `No successful reads (all 500)` → No data exposed

### 11. XSS Impact Assessment
- **Action:** Determine actual and potential impact of JavaScript injection
- **Depends On:** Steps 4, 8, 9
- **Pattern:** impact_assessment
- **Input:** outputs.js_verdict, outputs.validated_hypothesis, outputs.chain_assessment
- **Focus:** Session hijacking risk, credential theft potential, stored vs reflected XSS, log poisoning escalation to RCE, user data exposure
- **Output:** xss_impact_assessment

### 12. EDR Verification
- **Action:** Cross-reference with endpoint data if EDR available and LFI or log poisoning succeeded
- **Depends On:** Steps 7, 8, 10
- **Pattern:** integration_query
- **Integration:** edr
- **Condition:** IF outputs.lfi_verdict.succeeded == true OR outputs.chain_assessment.log_poisoning_chain == true
- **Focus:** Process execution history, web server process child processes, file system changes, unexpected command execution
- **Fields:** get_primary_device(alert), get_dst_ip(alert)
- **Output:** endpoint_verification
- **Parallel:** No

### Final Analysis ★
- **Sequential:** Must run in order

#### 13a. Detailed Analysis ★
- **Action:** Comprehensive technical synthesis of the investigation covering both attack vectors
- **Depends On:** All prior steps
- **Pattern:** threat_synthesis
- **Input:** ALL outputs
- **Focus:** Complete attack chain analysis, evidence correlation for both LFI and JS components, whether they form a coordinated chain, threat assessment, attacker sophistication
- **Output:** detailed_analysis

#### 13b. Disposition & Summary ★
- **Parallel:** Yes
- **Depends On:** Detailed Analysis
- **Actions:**
  - Determine verdict (TP/FP/Benign) with confidence score
  - Generate executive summary (128 chars max)
- **Pattern:** impact_assessment
- **Input:** outputs.detailed_analysis
- **Outputs:**
  - disposition: {verdict: "TP|FP|Benign", confidence: 0.0-1.0, escalate: true|false}
  - summary: "LFI+JS compound attack from ${get_src_ip(alert)} targeting ${get_primary_device(alert)} - [successful|unsuccessful] - [data exposed|XSS reflected|log poisoned|blocked]"

## Conditional Logic

### Branch: Log Poisoning RCE Chain (Highest Severity)
- **Condition:** outputs.chain_assessment.log_poisoning_chain == true AND outputs.lfi_verdict.log_file_accessed == true
- **Critical Actions:**
  - Immediate containment of affected host
  - Check if web application includes/processes log files
  - Search for evidence of code execution via poisoned log inclusion
  - Kill web server process if still running malicious code
  - Search for web shells or persistence mechanisms
  - Audit all file system changes since attack time
  - Escalate to incident response team immediately

### Branch: Successful LFI File Access
- **Condition:** outputs.lfi_verdict.succeeded == true AND outputs.response_patterns.any_status == 200
- **Critical Actions:**
  - Immediate containment of affected host
  - Check for additional file access attempts
  - Audit what files were successfully read
  - Search for follow-up exploitation (RCE, credential use, privilege escalation)
  - Escalate to incident response team

### Branch: Successful XSS Injection
- **Condition:** outputs.js_verdict.succeeded == true AND outputs.response_patterns.status == 200
- **Additional Steps:**
  - Check for stored XSS (payload persistence in database/logs)
  - Review session logs for potential hijacking
  - Search for credential theft indicators
  - Check for additional malicious payloads from same IP

### Branch: Credential Compromise
- **Condition:** outputs.lfi_exposure_assessment.shadow_accessed == true OR outputs.lfi_exposure_assessment.credentials_exposed == true
- **Critical Actions:**
  - Force password reset for ALL accounts
  - Rotate all application credentials and API keys
  - Audit all systems for lateral movement
  - Check for privilege escalation
  - Immediate escalation required

### Branch: Coordinated Chain - Both Vectors Unsuccessful
- **Condition:** outputs.lfi_verdict.succeeded == false AND outputs.js_verdict.succeeded == false AND outputs.chain_assessment.coordinated == true
- **Assessment:** True Positive (coordinated malicious attack) but both vectors blocked
- **Actions:**
  - Block source IP at firewall
  - Review WAF rules for both LFI and XSS coverage
  - Monitor for follow-up attacks with alternative techniques
  - Document attacker tooling and techniques

### Branch: Automated Scanner Detected
- **Condition:** outputs.validated_hypothesis == "Automated scanner" AND outputs.http_events.count > 50
- **Additional Steps:**
  - Verify if authorized security testing
  - Check scan schedule against detected time
  - If unauthorized, block source IP/ASN
  - Review WAF coverage to ensure compound payloads are blocked

### Branch: Unsuccessful Attack Pattern (Both Vectors Blocked)
- **Condition:** outputs.lfi_verdict.succeeded == false AND outputs.js_verdict.succeeded == false AND outputs.chain_assessment.coordinated == false
- **Fast Track:** True Positive (malicious intent) but unsuccessful - both payloads blocked
- **Actions:**
  - Block source IP at firewall
  - Confirm WAF rules are properly configured for both LFI and XSS patterns
  - Monitor for follow-up attacks

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR authorized_test_confirmed == true
- **Verification Steps:**
  - Check IT change management for scheduled penetration tests
  - Verify source IP matches known security vendor ranges
  - Contact security team to confirm authorization
  - If authorized → Mark as Benign with note covering both vectors
  - If not authorized → Escalate for unauthorized testing

## Investigation Notes

### Attack Vectors in This Alert

This detection rule fires on requests containing BOTH:
1. Path traversal sequences (`../`, `../../`, `/etc/passwd`, etc.)
2. Embedded JavaScript code (`<script>`, `javascript:`, event handlers, etc.)

These can represent:
- **Log poisoning RCE chain:** JS in User-Agent → LFI of log files → code execution
- **Polyglot payload:** Single payload designed to trigger multiple vulnerabilities
- **Automated fuzzer:** Tool simultaneously probing LFI and XSS in same request
- **Sequential exploitation:** Manual attacker combining known techniques

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for both LFI pattern and JS injection
2. **User-Agent analysis:** Critical for log poisoning detection (JS code in User-Agent)
3. **Response analysis:** Definitive indicator of success for both LFI (file content) and XSS (reflected payload)
4. **Path and parameter analysis:** Understanding which parameters carry which payload components
5. **Threat intelligence:** Context for attacker profile and tool attribution

### Common Patterns
- **Automated scanners:** High volume (50+ requests), multiple payload types, consistent timing, standard traversal targets
- **Manual testing:** Low volume (5-15 requests), focused on specific files, varied techniques, irregular timing
- **Log poisoning chain:** JS in User-Agent → Traversal to access.log/error.log → Follow-up inclusion with cmd parameter
- **Polyglot probe:** Single URL parameter containing both `../` traversal and `<script>` elements
- **Successful LFI:** Status 200 with non-zero response size containing file content
- **Successful XSS:** Status 200 with payload reflected in response body
- **Blocked attack:** Status 403 or consistent zero-byte responses

### Critical Indicators
- **Critical:** Log poisoning chain with file access success + code execution indicators
- **Critical:** /etc/shadow accessed (password hashes exposed)
- **High Priority:** /etc/passwd accessed + XSS injection both successful (compound breach)
- **Medium Priority:** Either LFI or XSS succeeded individually
- **Low Priority:** Both vectors attempted but blocked, or automated scanner (non-targeted)

### Investigation Efficiency
- Steps 2a and 2b can run in parallel (SIEM queries)
- Steps 3 and 4 can run after step 2 (parallel with each other)
- Steps 6a and 6b can run in parallel (threat intel lookups)
- Steps 7 and 8 can run in parallel after steps 3, 4, 5
- Step 12 (EDR) only runs if LFI succeeded or log poisoning detected
- Critical path: 1 → 2 → 3+4 → 5 → 7+8 → 9 → 13a → 13b
- Optional enrichment: 6a, 6b, 10, 11, 12

### Geo-Blocking Consideration
- If source IP is from unexpected geographic region with no business justification, consider geo-blocking
- For compound attacks (LFI + JS), recommend immediate IP block regardless of success

### Composition Provenance
- LFI investigation flow (steps 3, 7, 10, conditional branches) from `passwd-found-in-url-lfi-attack.md`
- JavaScript/XSS analysis (steps 4, 8, 11) from `xss-detection.md`
- Multi-technique chain assessment (step 5) adapted from `log-poisoning-rce-detection.md`
- Compound injection structure from `sql-injection-with-stored-xss-payload.md`
