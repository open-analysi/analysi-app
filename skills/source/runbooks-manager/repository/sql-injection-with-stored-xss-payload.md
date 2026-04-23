---
detection_rule: SQL Injection with Stored XSS Payload Detected
alert_type: Web Attack
subcategory: Injection
source_category: WAF
mitre_tactics: [T1190, T1059, T1189]
integrations_required: [siem]
integrations_optional: [threat_intel, edr]
version: 1.0.0
last_updated: 2025-11-17
author: runbook-match-agent
provenance:
  composition_strategy: hybrid_attack_blend
  blended_from:
    - sql-injection-detection.md (SQL injection analysis steps)
    - xss-detection.md (XSS payload analysis steps)
  confidence: MEDIUM
  reason: Composed from multiple relevant injection patterns for hybrid attack
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
      "time": "2024-01-15T14:32:00Z",
      "message": "SQL Injection with Stored XSS Payload Detected",
      "finding_info": {
        "title": "SQL Injection with Stored XSS Payload Detected",
        "uid": "ee0f1afe-20bb-4357-b0b8-9b7bf44c3ad0",
        "types": [
          "Web Attack",
          "Injection"
        ],
        "analytic": {
          "name": "SQL Injection with Stored XSS Payload Detected",
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
              "uid": "T1059",
              "name": "Command and Scripting Interpreter"
            },
            "tactic": {
              "uid": "TA0002",
              "name": "Execution"
            }
          },
          {
            "technique": {
              "uid": "T1189",
              "name": "Drive-by Compromise"
            },
            "tactic": {
              "uid": "TA0001",
              "name": "Initial Access"
            }
          }
        ],
        "desc": "Attacker attempting to inject malicious JavaScript code through SQL injection vector. Payload contains both SQL syntax and XSS script tags suggesting a chained attack to achieve persistent XSS via database storage."
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
      "observables": [
        {
          "name": "user_agent",
          "type_id": 16,
          "type": "HTTP User-Agent",
          "value": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }
      ],
      "evidences": [
        {
          "src_endpoint": {"ip": "45.142.212.61"},
          "url": {
            "url_string": "/api/products/search?q=%27%20UNION%20SELECT%20NULL%2C%20%27%3Cscript%3Ealert%28document.cookie%29%3C%2Fscript%3E%27%2C%20NULL--"
          },
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
          },
          "http_response": {
            "code": 200
          }
        }
      ],
      "raw_data": "{\"request_url\": \"/api/products/search?q=%27%20UNION%20SELECT%20NULL%2C%20%27%3Cscript%3Ealert%28document.cookie%29%3C%2Fscript%3E%27%2C%20NULL--\", \"src_ip\": \"45.142.212.61\", \"user_agent\": \"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36\", \"http_method\": \"GET\", \"response_status\": 200}"
    }
---
# SQL Injection with Stored XSS Payload Investigation Runbook

## Overview

This runbook investigates hybrid attacks combining SQL injection techniques with XSS payload delivery. The attacker attempts to inject malicious JavaScript code into the database via SQL injection, creating a persistent XSS vulnerability that executes when the stored data is later displayed to users.

**Attack Chain:**
1. SQL injection exploits database query
2. Malicious JavaScript payload injected into database field
3. Stored XSS triggers when data is retrieved and rendered

## Steps

![[common/universal/alert-understanding.md]]

![[common/by_source/waf-siem-evidence.md]]

### 2b. Hybrid Payload Pattern Analysis ★
- **Action:** Extract injection attempts and analyze both SQL and XSS patterns
- **Purpose:** Validates: "Automated scanner" vs "Targeted hybrid exploitation" vs "Stored XSS attack vector"
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Identify both SQL patterns (UNION, SELECT, quotes, comments) AND XSS patterns (script tags, event handlers, javascript: protocol) in the same payloads
- **Fields:** get_src_ip(alert)
- **Output:** hybrid_injection_attempts

### 3. Dual-Vector Payload Analysis ★
- **Action:** URL decode payloads and analyze both SQL injection and XSS components
- **Depends On:** Step 2b
- **Pattern:** payload_analysis
- **Input:** outputs.hybrid_injection_attempts.uri_query
- **Focus:**
  - SQL component: Identify injection techniques (UNION SELECT, OR-based, ORDER BY enumeration, comment terminators)
  - XSS component: Identify script injection methods (script tags, event handlers, obfuscation techniques)
  - Attack sophistication: Assess if this is a chained attack (SQL for injection + XSS for persistence)
  - Attack intent: Determine if goal is data extraction, stored XSS, or both
- **Output:** payload_analysis
- **Decision Points:**
  - `UNION SELECT with <script> tags` → Stored XSS via SQL injection
  - `Multiple columns tested` → Database enumeration for XSS injection point
  - `NULL placeholders with JavaScript` → Finding injectable column for script storage
  - `Obfuscated XSS in SQL context` → Advanced evasion techniques
  - `Simple patterns` → Scanner or basic testing
  - `Progressive complexity` → Manual targeted attack

![[common/evidence/threat-intel-enrichment.md]]

### 5. Hybrid Attack Success Determination ★
- **Action:** Determine success of both SQL injection and XSS payload delivery
- **Depends On:** Steps 2a, 2c, 3
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.payload_analysis, outputs.http_events
- **Decision Points:**
  - **SQL Injection Success:**
    - `status == 200 AND varying response sizes` → SQL injection likely succeeded
    - `status == 500 AND consistent sizes` → SQL syntax error (blocked)
    - `status == 200 AND response contains <script>` → Payload reflected (potential immediate XSS)
  - **Stored XSS Risk:**
    - `SQL injection successful + script payload` → HIGH risk of stored XSS
    - `Response reflects script tags unencoded` → Immediate XSS vulnerability
    - `Database write operation successful` → Payload may be stored
  - **Attack Pattern:**
    - `event_count > 50 in 30min` → Automated scanner
    - `event_count < 10 AND sophisticated payloads` → Targeted manual attack
    - `Progressive column enumeration (NULL, NULL, <script>)` → Systematic exploitation
- **Output:** attack_verdict

### 6. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 3, 4a (optional), 5
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.attack_verdict, outputs.payload_analysis, outputs.ip_reputation (if available)
- **Focus:**
  - Validate if this is stored XSS attack vector vs data extraction
  - Determine if attacker achieved database write access
  - Assess if XSS payload would execute when data is displayed
- **Output:** validated_hypothesis

### 7. Impact Assessment
- **Action:** Determine actual and potential impact of hybrid attack
- **Depends On:** Steps 5, 6
- **Pattern:** impact_assessment
- **Input:** outputs.attack_verdict, outputs.validated_hypothesis
- **Focus:**
  - **Immediate risks:** Data extraction, database compromise, reflected XSS
  - **Persistent risks:** Stored XSS affecting multiple users, session hijacking, credential theft
  - **Cascading risks:** If stored XSS successful, every user viewing the data becomes victim
  - **Compliance impact:** Data breach potential, PII/PHI exposure
  - **Remediation scope:** Database sanitization, application patching, affected user notification
- **Output:** impact_assessment

![[common/universal/final-analysis-trio.md]]
- **Summary Override:** "Hybrid SQL+XSS from ${get_src_ip(alert)} - [SQL: successful|unsuccessful] [XSS: stored risk|reflected|blocked]"

## Conditional Logic

### Branch: Successful Stored XSS Vector
- **Condition:** outputs.attack_verdict.sql_succeeded == true AND outputs.payload_analysis.contains_script_tags == true AND outputs.response_patterns.status == 200
- **Additional Steps:**
  - **CRITICAL:** Query database for stored malicious scripts
  - Identify affected database tables and columns
  - Search for any users who may have viewed the stored XSS
  - Check for session hijacking or credential theft indicators
  - Sanitize database entries containing script tags
  - Review all recent data modifications from source IP
  - Immediate escalation to incident response
  - Consider site-wide XSS scan

### Branch: SQL Injection Success but XSS Blocked
- **Condition:** outputs.attack_verdict.sql_succeeded == true AND outputs.payload_analysis.xss_encoded == true
- **Additional Steps:**
  - Verify HTML encoding/sanitization prevented XSS execution
  - Check for data extraction despite XSS failure
  - Review database logs for accessed tables
  - Assess what data may have been compromised via SQL injection alone

### Branch: Both Vectors Unsuccessful
- **Condition:** outputs.response_patterns.unique_sizes == 1 AND outputs.response_patterns.all_statuses == 500
- **Fast Track:** True Positive but unsuccessful - both SQL and XSS blocked, proceed to disposition without escalation

### Branch: Automated Security Scanner
- **Condition:** outputs.validated_hypothesis == "Automated vulnerability scanner" AND outputs.http_events.count > 100
- **Additional Steps:**
  - Verify if authorized security testing
  - Check scan schedule against detected time
  - Review for both SQL and XSS scanning signatures
  - Lower severity if authorized
  - If unauthorized, escalate for policy violation

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR outputs.abuse_history == null
- **Verification Steps:**
  - Check IT change management tickets for scheduled penetration testing
  - Verify source IP matches known security vendor ranges
  - Confirm testing scope includes SQL injection and XSS testing
  - If authorized → Mark as Benign with note documenting authorization
  - If not authorized → Escalate as critical unauthorized attack

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for attack pattern, progression, and success determination
2. **URL decoding:** Critical for understanding both SQL injection and XSS techniques
3. **Response pattern analysis:** Definitive indicator of SQL injection success
4. **Response content analysis:** Check if script tags appear unencoded in responses
5. **Database logs (if available):** Confirm data modification and script storage
6. **Threat intelligence:** Context for attacker profile and campaign indicators

### Hybrid Attack Patterns

**Classic Stored XSS via SQL Injection:**
```
UNION SELECT NULL, '<script>alert(document.cookie)</script>', NULL--
```
- NULL values find injectable columns
- Script tag placed in data column
- Comment (--) closes the SQL statement
- If successful, script stored in database and executes for all viewers

**Progressive Enumeration:**
1. Test basic SQL injection: `' OR 1=1--`
2. Enumerate columns: `' UNION SELECT NULL, NULL--` (adjust NULLs until no error)
3. Insert XSS payload: `' UNION SELECT NULL, '<script>...', NULL--`
4. Verify storage/reflection

### Attack Sophistication Indicators
- **Low:** Basic `<script>alert(1)</script>` in simple UNION
- **Medium:** Obfuscated JavaScript with proper column enumeration
- **High:** Multiple encoding layers, database-specific syntax, anti-WAF evasion
- **Advanced:** Polymorphic XSS payloads, time-delayed execution, multi-stage attacks

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (SIEM queries)
- Steps 4a, 4b can run in parallel (threat intel lookups)
- Critical path: 1 → 2 → 3 → 5 → 6 → 8a → 8b
- Optional enrichment: 4a, 4b, 7
- **Priority if stored XSS suspected:** Expedite database log review

### Unique Characteristics of Hybrid Attacks
- **Higher severity:** Two vulnerabilities exploited simultaneously
- **Persistence:** XSS payload survives as stored data (not just reflected)
- **Scalability:** One successful injection affects all users viewing the data
- **Detection complexity:** May trigger separate SQL and XSS alerts
- **Remediation complexity:** Requires both application patch AND database sanitization
