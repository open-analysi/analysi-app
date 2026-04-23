---
detection_rule: LS Command Detected in Requested URL
alert_type: Web Attack
subcategory: Command Injection
source_category: WAF
mitre_tactics: [T1190, T1059]
integrations_required: [siem, edr]
integrations_optional: [threat_intel]
version: 1.0.0
last_updated: 2025-11-16
author: ld-runbook-agent
source: soc167
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
      "time": "2022-02-27T00:36:00Z",
      "message": "LS Command Detected in Requested URL",
      "finding_info": {
        "title": "LS Command Detected in Requested URL",
        "uid": "8ae34122-0860-4554-88d0-ed4885087be0",
        "types": [
          "Web Attack"
        ],
        "analytic": {
          "name": "SOC167 - LS Command Detected in Requested URL",
          "type_id": 1,
          "type": "Rule"
        },
        "desc": "URL contains the string 'LS' which may indicate a command injection attempt. Alert triggered because the requested URL contains a substring matching the 'ls' command pattern."
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
        "hostname": "EliotPRD",
        "name": "EliotPRD",
        "ip": "188.114.96.15"
      },
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "172.16.17.46"
        },
        {
          "name": "dest_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "188.114.96.15"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://mycorp.io/blog/?s=skills"
        },
        {
          "name": "request_url",
          "type_id": 1,
          "type": "Hostname",
          "value": "mycorp.io"
        },
        {
          "name": "user_agent",
          "type_id": 16,
          "type": "HTTP User-Agent",
          "value": "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:24.0) Gecko/20100101 Firefox/24.0"
        }
      ],
      "raw_data": "Rule : SOC167 - LS Command Detected in Requested URL\nSeverity : High\nType : Web Attack\nEvent Time : Feb, 27, 2022, 12:36 AM\nHostname : EliotPRD\nDestination IP Address : 188.114.96.15\nSource IP Address : 172.16.17.46\nHTTP Request Method : GET\nRequested URL : https://mycorp.io/blog/?s=skills\nUser-Agent : Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:24.0) Gecko/20100101 Firefox/24.0\nAlert Trigger Reason : URL Contains LS\nDevice Action : Allowed",
      "evidences": [
        {
          "src_endpoint": {"ip": "172.16.17.46"},
          "dst_endpoint": {"ip": "188.114.96.15"},
          "url": {"url_string": "https://mycorp.io/blog/?s=skills"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:24.0) Gecko/20100101 Firefox/24.0"
          }
        }
      ],
      "unmapped": {
        "alert_trigger_reason": "URL Contains LS",
        "log_source": "HTTP Firewall Logs"
      }
    }
---
# LS Command Detected in Requested URL Investigation Runbook

## Steps

![[common/universal/alert-understanding.md]]

### 2a. URL Context Analysis ★
- **Action:** Examine the full URL to determine if "ls" appears in legitimate context
- **Purpose:** Validates: "Actual command injection" vs "Benign substring match"
- **Pattern:** payload_analysis
- **Input:** get_url(alert), finding_info.desc
- **Focus:** URL structure, query parameters, search terms, file paths where "ls" appears
- **Output:** url_context_analysis
- **Decision Points:**
  - `"ls" in common words (skills, false, results, tools)` → Likely false positive
  - `"ls" as standalone parameter or command` → Potential injection
  - `URL encoded "ls" (%6c%73)` → Possible evasion attempt
  - `"ls" with command syntax (;ls, |ls, &&ls)` → Strong injection indicator

### 2b. SIEM Traffic Context ★
- **Action:** Retrieve HTTP traffic history to establish baseline behavior
- **Purpose:** Validates: "Isolated anomaly" vs "Normal user behavior"
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Recent HTTP requests from source IP, accessed URLs, response codes, destination domains
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** traffic_history
- **Decision Points:**
  - `Multiple benign requests to same domain` → Likely legitimate browsing
  - `Single request with suspicious pattern` → Possible attack attempt
  - `All status 200 with normal response sizes` → Benign traffic pattern
  - `Mix of scanning/probing behavior` → Potential reconnaissance

### 2c. Response Pattern Analysis ★
- **Action:** Analyze HTTP response codes and sizes for command execution indicators
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Status codes, response sizes, error messages
- **Fields:** get_src_ip(alert), get_url(alert)
- **Output:** response_patterns
- **Decision Points:**
  - `status 200 with normal HTML response` → Application processed normally
  - `status 500 with error details` → Application rejected malformed input
  - `varying response sizes matching command output` → Possible successful injection

### 3. Endpoint Behavior Verification
- **Action:** Check endpoint activity for command execution or suspicious processes
- **Purpose:** Validates: "Command executed on system" vs "Blocked at application layer"
- **Pattern:** integration_query
- **Integration:** edr
- **Focus:** Command execution history, browser history, process logs matching timeframe
- **Fields:** get_primary_device(alert), get_src_ip(alert), time
- **Output:** endpoint_activity
- **Decision Points:**
  - `Browser history shows benign search activity` → False positive confirmed
  - `No "ls" command in shell history` → Not executed on system
  - `Shell commands match injection pattern` → Successful injection
  - `Normal web browsing activity` → Legitimate user behavior

![[common/evidence/threat-intel-enrichment.md]]

### 5. False Positive Determination ★
- **Action:** Determine if alert is false positive due to overly broad detection logic
- **Depends On:** Steps 2a, 2b, 2c, 3
- **Pattern:** impact_assessment
- **Input:** outputs.url_context_analysis, outputs.traffic_history, outputs.response_patterns, outputs.endpoint_activity (if available)
- **Decision Points:**
  - `"ls" in benign word AND normal traffic pattern AND no endpoint commands` → False Positive
  - `"ls" with command syntax AND varying responses` → True Positive (attempted injection)
  - `URL encoded "ls" OR command chaining syntax` → True Positive (evasion attempt)
  - `Internal source IP + benign browsing pattern` → Likely False Positive
  - `External IP + single suspicious request` → Possible True Positive
- **Output:** false_positive_verdict

### 6. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 2a, 2b, 2c, 5
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.url_context_analysis, outputs.false_positive_verdict
- **Output:** validated_hypothesis

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "LS command detection from ${get_src_ip(alert)} - [false positive from benign search|true positive injection attempt]"

## Conditional Logic

### Branch: Confirmed False Positive
- **Condition:** outputs.false_positive_verdict == "false_positive" AND outputs.url_context_analysis.benign_context == true
- **Fast Track:** False Positive - signature refinement needed
- **Actions:**
  - Document benign URL pattern that triggered alert
  - Close case with no escalation
  - Recommend signature tuning to exclude common word substrings
  - Add to false positive knowledge base

### Branch: True Positive Command Injection
- **Condition:** outputs.url_context_analysis.command_syntax == true OR outputs.response_patterns.injection_indicators == true
- **Critical Actions:**
  - Follow command injection investigation procedures
  - Check for successful command execution
  - Assess system compromise
  - Block source IP at firewall
  - Escalate to incident response

### Branch: Evasion Attempt Detected
- **Condition:** outputs.url_context_analysis.encoding_detected == true OR outputs.url_context_analysis.obfuscation == true
- **Assessment:** Sophisticated attack attempt using evasion techniques
- **Disposition:** True Positive - attempted attack (even if unsuccessful)
- **Actions:**
  - Block source IP immediately
  - Check for other evasion patterns from same source
  - Review WAF/IDS rules for bypass attempts

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
1. **URL structure:** Primary indicator of false positive vs true positive
2. **SIEM traffic history:** Context for determining user behavior pattern
3. **Endpoint activity:** Definitive proof command did/did not execute
4. **Response analysis:** Secondary indicator of application behavior

### Common False Positive Patterns
- **Benign substrings:** "ls" in words like skills, false, tools, results, details
- **Search queries:** Blog searches, product searches containing "ls"
- **Internal traffic:** Corporate users browsing legitimate sites
- **Normal response patterns:** Status 200 with consistent response sizes

### True Positive Indicators
- **Command syntax:** ;ls, |ls, &&ls, `ls`, $(ls)
- **URL encoding:** %6c%73, %4c%53 (obfuscation attempt)
- **Standalone parameter:** ?cmd=ls, &exec=ls
- **Response anomalies:** Varying sizes suggesting command output
- **External source:** Non-corporate IP with single suspicious request

### Critical Indicators
- **High Priority:** URL encoded commands or command chaining syntax
- **Medium Priority:** Standalone "ls" parameter from external IP
- **Low Priority:** "ls" substring in common words from internal IP

### Signature Tuning Recommendations
- **Improve detection logic:** Match "ls" only when:
  - Preceded/followed by command separators (;, |, &&, `, $)
  - Used as standalone parameter value
  - URL encoded or obfuscated
  - NOT when embedded in common English words
- **Add whitelisting:** Common search terms and URL patterns
- **Context awareness:** Consider source IP reputation and traffic history

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 3 and 4a, 4b can run in parallel (EDR + threat intel lookups)
- Critical path: 1 → 2a → 5 → 6 → 7a → 7b
- Optional enrichment: 3, 4a, 4b (helpful but not required for false positive determination)
