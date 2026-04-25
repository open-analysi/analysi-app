---
detection_rule: SQL Injection Leading to OS Command Execution Detected
alert_type: Web Attack
subcategory: Injection
source_category: WAF
mitre_tactics: [T1190, T1059, T1505]
integrations_required: [siem, edr]
integrations_optional: [threat_intel]
version: 1.0.0
author: runbook-match-agent
source: composed
provenance:
  composition_strategy: chained_attack_pivot_blend
  blended_from:
    - sql-injection-detection.md (SQL injection payload analysis and success determination)
    - command-injection-detection.md (OS command execution verification and credential impact)
    - sql-injection-with-stored-xss-payload.md (hybrid attack structure and dual-vector verdict)
    - log-poisoning-rce-detection.md (RCE evidence collection pattern)
  confidence: MEDIUM
  reason: >
    No exact detection_rule match. Composed from multiple high-scoring Injection/WAF runbooks
    covering both SQL injection and OS command execution phases. The pivot from database
    access to OS-level command execution (xp_cmdshell, LOAD_FILE) requires investigation of
    both attack phases in sequence, blending patterns from all four top-scoring candidates.
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
      "time": "2026-04-26T11:45:00Z",
      "message": "SQL Injection Leading to OS Command Execution Detected",
      "finding_info": {
        "title": "SQL Injection Leading to OS Command Execution Detected",
        "types": ["Web Attack"],
        "analytic": {
          "name": "SQL Injection Leading to OS Command Execution Detected",
          "type_id": 1,
          "type": "Rule"
        },
        "attacks": [
          {"technique": {"uid": "T1190", "name": "Exploit Public-Facing Application"}},
          {"technique": {"uid": "T1059", "name": "Command and Scripting Interpreter"}},
          {"technique": {"uid": "T1505", "name": "Server Software Component"}}
        ],
        "desc": "WAF detected SQL injection patterns combined with OS command execution indicators. Payload contains UNION SELECT with xp_cmdshell or LOAD_FILE commands, suggesting attacker is attempting to pivot from database access to OS-level command execution."
      },
      "metadata": {
        "version": "1.8.0",
        "product": {"name": "Security Detection", "vendor_name": "Unknown"},
        "labels": ["source_category:WAF"]
      },
      "device": {
        "hostname": "WebDB-Prod-01",
        "name": "WebDB-Prod-01"
      },
      "evidences": [
        {
          "src_endpoint": {"ip": "198.51.100.23"},
          "dst_endpoint": {"ip": "10.10.50.15"},
          "url": {"url_string": "https://app.example.com/products?id=1'+UNION+SELECT+NULL,xp_cmdshell('whoami'),NULL--"},
          "http_request": {
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          }
        }
      ],
      "observables": [
        {
          "name": "primary_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "198.51.100.23"
        },
        {
          "name": "dest_ip",
          "type_id": 2,
          "type": "IP Address",
          "value": "10.10.50.15"
        },
        {
          "name": "request_url",
          "type_id": 6,
          "type": "URL String",
          "value": "https://app.example.com/products?id=1'+UNION+SELECT+NULL,xp_cmdshell('whoami'),NULL--"
        }
      ]
    }
---
# SQL Injection Leading to OS Command Execution Investigation Runbook

## Overview

This runbook investigates a chained attack where SQL injection is used as the initial vector to gain database access, then pivoted to OS-level command execution. The attack combines UNION SELECT techniques with database stored procedures (e.g., `xp_cmdshell` on MSSQL, `LOAD_FILE`/`INTO OUTFILE` on MySQL) to execute arbitrary OS commands or read/write files on the server.

**Attack Chain:**
1. SQL injection exploits a database query (UNION SELECT, OR-based, ORDER BY)
2. Database stored procedure or function used to execute OS commands (xp_cmdshell, LOAD_FILE, sys_exec)
3. OS command output returned via HTTP response or written to a web-accessible file
4. Potential persistence via web shell installation (T1505)

## Steps

### 1. Alert Understanding & Initial Assessment ★
- **Action:** Analyze alert and form investigation hypotheses
- **Pattern:** hypothesis_formation
- **Input:** finding_info.title, severity, get_src_ip(alert), get_dst_ip(alert), get_url(alert), get_http_method(alert), get_user_agent(alert), finding_info.desc
- **Outputs:**
  - context_summary: Human-readable alert summary
  - investigation_hypotheses: List of theories to investigate
  - key_observables: Key indicators from the alert
- **Initial Hypotheses to Form:**
  - H1: Attacker successfully pivoted from SQLi to OS command execution (critical TP)
  - H2: SQLi succeeded but OS pivot failed (partial attack — database access only)
  - H3: SQLi attempted but blocked entirely (unsuccessful TP)
  - H4: Authorized penetration testing activity (FP/Benign)
  - H5: Automated vulnerability scanner probing (TP — malicious but unsophisticated)

### 2. Supporting Evidence Collection ★
- **Purpose:** Collect SIEM data to validate hypotheses and identify full attack scope
- **Parallel:** Yes

#### 2a. SIEM Event Retrieval ★
- **Action:** Retrieve all HTTP requests from attacker IP to identify attack pattern and sequence
- **Purpose:** Validates attack progression and identifies full scope of requests
- **Pattern:** integration_query
- **Integration:** siem
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** http_events

#### 2b. SQL Injection Payload Pattern Analysis ★
- **Action:** Extract SQL injection attempts and identify OS pivot indicators
- **Purpose:** Validates: "Automated scanner" vs "Targeted SQLi-to-OS pivot exploitation"
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** SQL patterns (UNION SELECT, OR, quotes, comment terminators), OS execution functions (xp_cmdshell, LOAD_FILE, INTO OUTFILE, sys_exec, UTL_FILE), URL encoding (%27, %3B, %2C), command chaining in SQL context
- **Fields:** get_src_ip(alert)
- **Output:** sqli_payload_analysis
- **Decision Points:**
  - `UNION SELECT with xp_cmdshell` → MSSQL OS command pivot attempt
  - `LOAD_FILE or INTO OUTFILE` → MySQL file read/write pivot attempt
  - `sys_exec or DBMS_SCHEDULER` → Oracle/PostgreSQL OS execution attempt
  - `Multiple payload variations` → Systematic enumeration
  - `Single payload type` → Manual targeted attempt or automated single-check

#### 2c. Response Pattern Analysis ★
- **Action:** Analyze HTTP response patterns to detect successful exploitation
- **Purpose:** Validates attack success vs failure at both SQL and OS pivot layers
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Response sizes, status codes, patterns indicating exploitation success
- **Fields:** get_src_ip(alert)
- **Output:** response_patterns

### 3. SQL Injection Phase Analysis ★
- **Action:** URL decode payloads and analyze the SQL injection component
- **Depends On:** Step 2b
- **Pattern:** payload_analysis
- **Input:** outputs.sqli_payload_analysis.uri_query, outputs.sqli_payload_analysis.post_body
- **Focus:**
  - SQL injection technique: UNION-based, error-based, blind boolean, time-based
  - Database fingerprinting payloads: DB-specific syntax revealing target database type
  - OS pivot mechanism: Which stored procedure or function is used and how
  - Column enumeration: Number of columns in UNION statement
  - Payload sophistication: Manual targeted vs automated scanner signatures
- **Output:** sql_payload_analysis
- **Decision Points:**
  - `xp_cmdshell in UNION SELECT` → MSSQL target, direct OS execution
  - `LOAD_FILE or INTO OUTFILE with webroot path` → MySQL, file read or web shell write
  - `ORDER BY N enumeration before UNION` → Systematic column count determination
  - `NULL placeholders with xp_cmdshell` → Targeted column identification for OS pivot
  - `Obfuscated encoding` → Evasion-aware attacker
  - `Simple patterns without column enumeration` → Scanner or unsophisticated attempt

### 4. OS Command Execution Phase Analysis ★
- **Action:** Extract and analyze the OS commands injected via the SQL pivot mechanism
- **Depends On:** Steps 2b, 3
- **Pattern:** payload_analysis
- **Input:** outputs.sqli_payload_analysis, outputs.sql_payload_analysis
- **Focus:**
  - Commands passed to xp_cmdshell, sys_exec, or written via INTO OUTFILE
  - Command types: reconnaissance (whoami, hostname, ipconfig, uname), credential access (cat /etc/passwd, cat /etc/shadow, net user), lateral movement setup (net use, wget, curl), persistence (echo webshell content)
  - Command progression: Single command vs sequential escalating commands
  - Web shell write indicators: INTO OUTFILE targeting web-accessible directories
- **Output:** os_command_analysis
- **Decision Points:**
  - `whoami, hostname, uname, ipconfig` → Reconnaissance phase — post-pivot confirmation
  - `cat /etc/shadow or net user /domain` → Credential theft attempt
  - `wget, curl with external URL` → Payload download (potential implant)
  - `INTO OUTFILE '/var/www/html/shell.php'` → Web shell installation (T1505)
  - `net use, psexec indicators` → Lateral movement preparation
  - `Single reconnaissance command` → Initial pivot test, early stage attack

### 5. Threat Intelligence Enrichment
- **Parallel:** Yes
- **Optional:** Both sources can fail gracefully

#### 5a. IP Reputation Check
- **Action:** Check attacker IP reputation in threat intelligence sources
- **Purpose:** Validates threat actor profile and attribution
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** ip_reputation

#### 5b. IP Abuse History & Geolocation
- **Action:** Check IP abuse history and geographic location from threat databases
- **Purpose:** Context for attacker origin, history, and campaign indicators
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** geo_abuse_data

### 6. OS Command Execution Verification ★
- **Action:** Cross-reference with endpoint data to confirm OS command execution occurred
- **Depends On:** Steps 3, 4
- **Pattern:** integration_query
- **Integration:** edr
- **Condition:** IF EDR available AND (outputs.sql_payload_analysis.pivot_mechanism != null)
- **Focus:** Process execution history on target host — specifically child processes spawned by the database service or web server process, matching injected commands
- **Fields:** get_primary_device(alert), get_dst_ip(alert)
- **Output:** os_execution_evidence
- **Decision Points:**
  - `Database process spawned cmd.exe or /bin/sh` → Confirmed OS pivot
  - `Commands match injected payloads` → Definitive execution confirmed
  - `No child process evidence` → OS pivot may have failed
  - `Commands executed as SYSTEM or root` → Full system compromise
  - `Commands executed as db service account` → Constrained but still significant

### 7. Attack Success Determination ★
- **Action:** Determine if both the SQL injection and OS pivot succeeded
- **Depends On:** Steps 2a, 2c, 3, 4, 6
- **Pattern:** impact_assessment
- **Input:** outputs.response_patterns, outputs.sql_payload_analysis, outputs.os_command_analysis, outputs.os_execution_evidence
- **Decision Points:**
  - **SQL Injection Success:**
    - `status == 200 AND varying response sizes` → SQL injection likely succeeded
    - `response contains command output (uid=, Directory of, hostname)` → SQLi + OS pivot confirmed
    - `status == 500 AND consistent response sizes` → SQL syntax error, injection blocked
    - `status == 403` → WAF blocked request
  - **OS Pivot Success:**
    - `EDR confirms child process from DB service` → Definitive OS pivot
    - `Response contains recognizable OS command output` → Definitive OS pivot via HTTP
    - `INTO OUTFILE confirmed with subsequent web shell access` → File write + persistence
    - `No EDR evidence AND response size consistent` → OS pivot likely failed
  - **Attack Pattern:**
    - `event_count > 50 in 30min` → Automated scanner
    - `event_count < 10 AND progressive complexity` → Manual targeted attack
    - `Immediate pivot without column enumeration` → Prior reconnaissance or known target
- **Output:** attack_verdict

### 8. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Depends On:** Steps 1, 4, 5a (optional), 7
- **Pattern:** evidence_correlation
- **Input:** outputs.investigation_hypotheses, outputs.attack_verdict, outputs.sql_payload_analysis, outputs.os_command_analysis, outputs.ip_reputation (if available)
- **Output:** validated_hypothesis

### 9. Compromise & Persistence Assessment
- **Action:** Determine scope of compromise and persistence mechanisms if OS execution succeeded
- **Depends On:** Steps 4, 6, 7, 8
- **Pattern:** impact_assessment
- **Input:** outputs.os_command_analysis, outputs.os_execution_evidence, outputs.attack_verdict
- **Focus:**
  - Commands executed and their impact (credential access, data exfiltration, lateral movement)
  - Web shell installation indicators (file writes to web-accessible directories)
  - Backdoor or scheduled task creation
  - Privilege level of executed commands
  - Data exfiltration via SQL (UNION SELECT with sensitive table data)
- **Output:** compromise_assessment
- **Decision Points:**
  - `/etc/shadow or SAM hive accessed` → Credentials compromised
  - `INTO OUTFILE targeting webroot` → Web shell installed (T1505)
  - `wget/curl to external host` → Payload downloaded
  - `Reconnaissance only (whoami, hostname)` → Early stage, no confirmed exfiltration
  - `UNION SELECT on sensitive tables (users, passwords, credit_cards)` → Data exfiltration via SQLi

### Final Analysis ★
- **Sequential:** Must run in order

#### Detailed Analysis ★
- **Action:** Comprehensive technical synthesis of the investigation
- **Depends On:** All prior steps
- **Pattern:** threat_synthesis
- **Input:** ALL outputs
- **Focus:** Complete attack chain analysis (SQLi vector → OS pivot mechanism → commands executed → impact), evidence correlation across SIEM and EDR, threat assessment including persistence and lateral movement risk
- **Output:** detailed_analysis

#### Disposition & Summary ★
- **Parallel:** Yes
- **Depends On:** Detailed Analysis
- **Actions:**
  - Determine verdict (TP/FP/Benign) with confidence score
  - Generate executive summary (128 chars max)
- **Pattern:** impact_assessment
- **Input:** outputs.detailed_analysis
- **Outputs:**
  - disposition: {verdict: "TP|FP|Benign", confidence: 0.0-1.0, escalate: true|false}
  - summary: "SQLi+OS pivot from ${get_src_ip(alert)} - [SQL: success|blocked] [OS: executed|failed] - [impact]"

## Conditional Logic

### Branch: Full Compromise — SQLi + OS Execution Confirmed
- **Condition:** outputs.attack_verdict.sql_succeeded == true AND outputs.attack_verdict.os_pivot_succeeded == true
- **Critical Actions:**
  - Immediate containment of affected host and database server
  - Kill any spawned processes from database service
  - Search for web shells or persistence mechanisms installed via INTO OUTFILE
  - Audit all file system changes on target host since attack time
  - Review all database queries for data exfiltration (SELECT on sensitive tables)
  - Check for lateral movement from compromised host
  - Force rotation of all credentials accessible from the host
  - Escalate to incident response team immediately

### Branch: SQLi Succeeded but OS Pivot Failed
- **Condition:** outputs.attack_verdict.sql_succeeded == true AND outputs.attack_verdict.os_pivot_succeeded == false
- **Actions:**
  - Assess what database data was accessed or exfiltrated via UNION SELECT
  - Review database logs for sensitive table queries
  - Block source IP at perimeter
  - Verify xp_cmdshell is disabled (MSSQL) or FILE privilege revoked (MySQL)
  - Assess database privilege level of compromised account

### Branch: Both Vectors Unsuccessful
- **Condition:** outputs.response_patterns.all_statuses == 500|403 AND outputs.os_execution_evidence == null
- **Fast Track:** True Positive (malicious intent) but unsuccessful — WAF or application blocked
- **Actions:**
  - Block source IP at firewall
  - Review WAF rule tuning for injection detection
  - Monitor for follow-up attacks from same IP range

### Branch: Web Shell Installed (T1505)
- **Condition:** outputs.compromise_assessment.webshell_indicators == true OR outputs.os_execution_evidence.suspicious_files_created == true
- **Critical Actions:**
  - Immediately locate and remove web shell files from all web-accessible directories
  - Full forensic analysis of affected host
  - Check for backdoor database accounts
  - Review all web-accessible directories for malicious files
  - Audit all requests to web shell path in SIEM for additional attacker activity
  - Consider full host rebuild

### Branch: Credential Compromise
- **Condition:** outputs.compromise_assessment.credentials_accessed == true
- **Critical Actions:**
  - Force immediate password reset for ALL accounts on compromised host
  - Rotate all application credentials, API keys, and database passwords
  - Audit all systems for lateral movement from the date of compromise
  - Check for privilege escalation or new account creation

### Branch: Automated Security Scanner
- **Condition:** outputs.validated_hypothesis == "Automated vulnerability scanner" AND outputs.http_events.count > 50
- **Additional Steps:**
  - Verify if authorized security testing via change management tickets
  - Check scan schedule against detected time
  - Verify source IP matches known security vendor ranges
  - If authorized → Mark as Benign with note documenting authorization
  - If unauthorized → Escalate for unauthorized penetration testing

### Branch: Authorized Security Testing
- **Condition:** outputs.ip_reputation.category == "security_scanner" OR outputs.geo_abuse_data.abuse_reports == 0
- **Verification Steps:**
  - Check IT change management for scheduled penetration tests
  - Verify source IP matches known security vendor ranges
  - Contact security team to confirm authorization
  - If authorized → Mark as Benign with note
  - If not authorized → Escalate as critical unauthorized attack

## Investigation Notes

### Key Evidence Sources
1. **SIEM HTTP logs:** Primary evidence for SQL injection payloads, OS pivot technique, and response analysis
2. **EDR process history:** Definitive proof of OS command execution — look for DB service process spawning shell processes
3. **Payload decoding:** Critical for identifying both SQL technique and OS commands used
4. **Response pattern analysis:** Indicator of attack success (varying sizes = different command outputs)
5. **Database service logs (if available):** Confirm xp_cmdshell execution or file operations

### Attack Chain Patterns

**MSSQL xp_cmdshell Pivot (Classic):**
```
' UNION SELECT NULL, xp_cmdshell('whoami'), NULL--
' UNION SELECT NULL, xp_cmdshell('net user /domain'), NULL--
```

**MySQL LOAD_FILE Read / INTO OUTFILE Write:**
```
' UNION SELECT LOAD_FILE('/etc/passwd'), NULL, NULL--
' UNION SELECT '<?php system($_GET["c"]); ?>', NULL, NULL INTO OUTFILE '/var/www/html/shell.php'--
```

**Progressive Attack Progression:**
1. Column count enumeration: `ORDER BY N--` until error
2. Database fingerprinting: DB-version specific functions
3. xp_cmdshell enable (if disabled): `EXEC sp_configure 'show advanced options', 1; RECONFIGURE`
4. OS command reconnaissance: `xp_cmdshell('whoami')`
5. Credential or data access: `xp_cmdshell('net user')` or direct table UNION SELECT
6. Persistence: web shell via file write or scheduled task creation

### MITRE ATT&CK Coverage
- **T1190** (Exploit Public-Facing Application): SQL injection as initial access vector
- **T1059** (Command and Scripting Interpreter): OS command execution via SQLi pivot
- **T1505** (Server Software Component): Web shell installation via INTO OUTFILE or xp_cmdshell

### Common Patterns
- **Full pivot confirmed:** Status 200 + response contains OS output (uid=, Directory of) + EDR child process evidence
- **SQL success, OS pivot blocked:** xp_cmdshell disabled or MySQL FILE privilege not granted
- **Automated scanner:** High volume (50+ requests), multiple payload types, all returning 500/403
- **Manual targeted attack:** Low volume, progressive complexity, database-specific evasion

### Critical Indicators
- **Critical:** OS command execution confirmed with credential access, web shell installation, or data exfiltration
- **High Priority:** OS command execution confirmed with reconnaissance only (early stage)
- **Medium Priority:** SQL injection succeeded but OS pivot failed — assess data exposure
- **Low Priority:** Both vectors blocked — unsuccessful TP

### Investigation Efficiency
- Steps 2a, 2b, 2c can run in parallel (all SIEM queries)
- Steps 5a, 5b can run in parallel (threat intel lookups)
- Step 6 (EDR) is conditional — only run if SQLi + pivot indicators found
- Critical path: 1 → 2 → 3 → 4 → 7 → 8 → 9 → Final Analysis
- Optional enrichment: 5a, 5b
- Step 6 (EDR) gates on attack_verdict confidence — run in parallel with step 9 if EDR available
