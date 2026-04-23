# Web Attacks Investigation Guide

## Overview

75% of the attacks inside an enterprise are usually on Web-Apps. This guide covers detection and investigation techniques for common web attack types.

## Common Web Attack Types

### OWASP Top 10 (2021)

1. Broken Access Control
2. Cryptographic Failures
3. Injection
4. Insecure Design
5. Security Misconfiguration
6. Vulnerable and Outdated Components
7. Identification and Authentication Failures
8. Software and Data Integrity Failures
9. Security Logging and Monitoring Failures
10. Server-Side Request Forgery (SSRF)

### Common Attack Vectors

- SQL Injection
- Cross Site Scripting (XSS)
- Command Injection
- IDOR (Insecure Direct Object Reference)
- RFI & LFI (Remote/Local File Inclusion)
- File Upload (Web Shell)
- Open Redirection

## HTTP Protocol Basics

### HTTP Request Components

1. **Request Line**: HTTP method and requested resource
2. **Request Headers**: Headers that the server will process
3. **Request Message Body**: Data to be sent to the server

### Key HTTP Request Headers

- **Host**: Identifies which domain the requested resource belongs to
- **Cookie**: Stores session information
- **User-Agent**: Contains browser and operating system information (can reveal automated scanners)
- **Accept**: Type of data requested
- **Accept-Encoding**: Encoding types accepted by client
- **Connection**: How the HTTP connection is handled (close, keep-alive)

### HTTP Response Components

1. **Status Line**: HTTP version and status code
2. **Response Headers**: Various headers for different purposes
3. **Response Body**: The requested resource

### HTTP Status Codes

- **100-199**: Informational responses
- **200-299**: Successful responses
- **300-399**: Redirection messages (302 to /login.php can indicate successful login)
- **400-499**: Client error responses
- **500-599**: Server error responses

## SQL Injection Attacks

### What is SQL Injection?

SQL Injections are critical attack vectors in which a web application directly includes unsanitized user-provided data in SQL queries.

### Example Payload

```
' OR 1=1 -- -
```

This payload bypasses authentication by making the WHERE clause always true.

### What Attackers Gain

- Authentication bypass
- Command execution (via xp_cmdshell, etc.)
- Exfiltration of sensitive data
- Creating/Deleting/Updating database entries

### Detection Methods

**Manual Inspection**:
- Check all areas that come from the user (not just forms - also headers like User-Agent)
- Look for SQL keywords: INSERT, SELECT, WHERE, UNION, CHR
- Check for special characters: apostrophes ('), dashes (-), parentheses
- Familiarize yourself with commonly used SQL injection payloads

**Automated Tool Detection**:
- Look at User-Agent header (tools often include their name/version)
- Check frequency of requests (automated tools send many requests per second)
- Look at payload content (may include tool names like "sqlmap")
- Complex payloads often indicate automated scanning

### Investigation Example

**Indicators to check**:
1. Look for % symbols (URL encoding) in requested pages
2. Decode URL-encoded requests to see SQL keywords clearly
3. Check request timing (50+ requests in 1 second = automated)
4. Examine payload complexity (complex = likely automated)
5. **Determining success**: Look at HTTP response size - noticeable differences may indicate successful attack

**IMPORTANT**: It is not wise to upload access logs containing critical information to 3rd party web applications for decoding.

## Cross-Site Scripting (XSS)

### Types of XSS

1. **Reflected XSS (Non-Persistent)**: Payload must be present in the request. Most common type.
2. **Stored XSS (Persistent)**: Attacker can permanently upload the XSS payload. Most dangerous.
3. **DOM Based XSS**: Attack payload executed via modifying the DOM environment

### Example Payloads

```html
<script>alert(1)</script>
<script>window.location='https://malicious.com'</script>
```

### What Attackers Gain

- Steal user's session information
- Capture credentials
- Redirect users to malicious sites

### Detection Methods

- Look for keywords: "alert", "script"
- Learn commonly used XSS payloads
- Check for special characters: greater than (>), less than (<)

**Note**: Without access to HTTP responses, determining success is difficult.

## Command Injection

### What is Command Injection?

Attacks that occur when data received from a user is not sanitized and is passed directly to the operating system shell.

### Example Payloads

```bash
""; system('whoami')
""; system('net user')
""; system('net user hacker Asd123!! /add')
```

### What Attackers Gain

- Execute commands on the operating system
- Create reverse shells
- Stop services or delete critical files
- Full system compromise

### Detection Methods

- Check all areas of web request
- Look for terminal command keywords: dir, ls, cp, cat, type, whoami, net user, etc.
- Learn commonly used command injection payloads (especially reverse shell commands)
- Check unusual headers (e.g., bash commands in User-Agent header - Shellshock vulnerability)

### Investigation Example

**Command Injection Indicators in Logs**:
```
message=""; system('whoami')
message=""; system('net user')
message=""; system('net share')
message=""; system('net user hacker Asd123!! /add')
```

**Analysis Pattern**:
- Attacker checks current user (whoami)
- Lists user accounts (net user)
- Lists shared resources (net share)
- Attempts to add new user account (net user hacker /add)
- Repeated commands may indicate failed execution or confirmation attempts

## Insecure Direct Object Reference (IDOR)

### What is IDOR?

A vulnerability caused by absence or improper use of authorization mechanism, allowing one person to access objects belonging to another. Listed as #1 in OWASP 2021 ("Broken Access Control").

### Example

```
URL: https://example.com/get_user_information?id=1
```

If changing `id=2` or `id=3` allows access to other users' information without authorization check, this is IDOR.

### What Attackers Gain

- Steal personal information
- Access unauthorized documents
- Take unauthorized actions (deleting, modifying)

### Detection Methods

**IDOR is harder to detect than other attacks** because it lacks specific payloads like SQL injection or XSS.

- **Check all parameters**: IDOR can occur in any parameter
- **Look at request frequency**: Many requests to same page from one source (brute-force pattern)
- **Find patterns**: Sequential predictable values (id=1, id=2, id=3, etc.)

**Note**: HTTP responses would help identify IDOR attacks, but are not usually logged.

### Investigation Example

**Analyzing WordPress IDOR Attack**:
```
GET /blog/wp-admin/user-edit.php?user_id=15 HTTP/1.1" 302 5692 "-" "wfuzz/3.1.0"
GET /blog/wp-admin/user-edit.php?user_id=7 HTTP/1.1" 302 5691 "-" "wfuzz/3.1.0"
GET /blog/wp-admin/user-edit.php?user_id=29 HTTP/1.1" 302 5692 "-" "wfuzz/3.1.0"
```

**Analysis**:
- Many different user_id parameters (abnormal)
- User-Agent shows "wfuzz/3.1.0" (automated tool)
- 15-16 requests in short timeframe (automated)
- Response code 302 (redirect) vs. expected 200 (success)
- Response sizes very similar (5691-5692 bytes) - likely unsuccessful
- User information would have varying sizes if successful

## Remote/Local File Inclusion (RFI/LFI)

### What is LFI?

Local File Inclusion occurs when a file is included without sanitizing user data. The file is on the same web server as the web application.

### What is RFI?

Remote File Inclusion occurs when a file is included without sanitizing user data. The included file is hosted on another server.

### Example LFI Payload

```
Payload: /../../../../../../../../../etc/passwd%00
```

Uses "../" to traverse to parent directories, reaching root directory and including sensitive files like /etc/passwd.

### What Attackers Gain

- Executing code
- Disclosure of sensitive information
- Denial of Service

### Detection Methods

- Examine all fields in web request
- Look for special characters: '/', '.', '\\'
- Become familiar with commonly targeted files (/etc/passwd, /etc/shadow, etc.)
- Look for HTTP/HTTPS protocols (indicates RFI - attacker hosting file on their server)

## Web Shell Upload (File Upload Attacks)

### What is a Web Shell?

Malicious code written in the web server's language (PHP, ASP, JSP, etc.) that allows remote code execution and system control after upload.

### How Attackers Upload Web Shells

**Common Upload Vectors**:
- File upload forms (avatars, documents, media)
- Content management system vulnerabilities
- Plugin/theme upload directories
- Exploiting file inclusion vulnerabilities

**Bypass Techniques**:
- Filename manipulation (.php.jpg, .phtml, .php5)
- MIME type spoofing
- Double extension tricks
- Null byte injection (.php%00.jpg)
- Case sensitivity (PHP vs php)

### What Attackers Gain

- **Remote Code Execution**: Run system commands
- **Persistence**: Maintain access even after other vulnerabilities patched
- **Data Exfiltration**: Download sensitive files
- **Lateral Movement**: Attack other internal systems
- **Privilege Escalation**: Elevate to root/admin
- **Backdoor Access**: Bypass authentication

### Detection Methods

**Log Analysis**:

**Monitor web server access logs for suspicious paths**:
```
/wp-content/uploads/sp-client-document-manager/shell.php
/uploads/malicious.php
/images/cmd.php
/temp/webshell.aspx
```

**Indicators**:
- Requests to recently uploaded files
- POST requests to upload directories
- Parameters like `cmd=`, `exec=`, `command=`
- Base64 encoded data in requests

**File System Monitoring**:
- New .php/.asp/.jsp files in upload directories
- Files with suspicious names (shell, cmd, backdoor, c99, r57)
- Recently modified web files
- Files with unusual permissions

**Network Traffic**:
- Connections from web server process to external IPs
- Unusual outbound connections
- Data exfiltration patterns
- C2 communication

### Investigation Example

**Detection Scenario**:
- Alert: Suspicious file upload to WordPress plugin directory
- Path: `/wp-content/uploads/sp-client-document-manager/shell.php`
- Source IP: 203.0.113.42

**Investigation Steps**:

1. **Check upload logs**:
   - When was file uploaded?
   - What IP uploaded it?
   - What was original filename?

2. **Analyze file** (DO NOT execute):
   - Download for static analysis
   - Check for known web shell signatures
   - Look for functions: `system()`, `exec()`, `shell_exec()`, `eval()`
   - Search for Base64 encoded sections

3. **Check access logs**:
   - Has anyone accessed the uploaded file?
   - What commands were executed?
   - What data was downloaded?

4. **Search for additional shells**:
   - Attacker may upload multiple shells
   - Check entire web directory
   - Look for recently modified files

5. **Check for post-exploitation**:
   - New user accounts created?
   - Scheduled tasks/cron jobs?
   - Modified system files?
   - Lateral movement attempts?

### Common Web Shell Indicators

**PHP Web Shells**:
```php
<?php system($_GET['cmd']); ?>
<?php eval($_POST['code']); ?>
<?php echo shell_exec($_REQUEST['command']); ?>
```

**Functions to look for**:
- `system()`, `exec()`, `passthru()`, `shell_exec()`
- `eval()`, `assert()`, `create_function()`
- `base64_decode()` (often used for obfuscation)
- `file_get_contents()`, `file_put_contents()`

**ASP/ASPX Web Shells**:
```asp
<%@ Page Language="C#" %>
<% Response.Write(Request["cmd"]); %>
```

**JSP Web Shells**:
```jsp
<% Runtime.getRuntime().exec(request.getParameter("cmd")); %>
```

### Response Actions

**Immediate**:
1. Block source IP at firewall
2. Remove web shell file
3. Check for additional shells
4. Disable upload functionality temporarily

**Investigation**:
5. Analyze web shell capabilities
6. Review access logs for all executions
7. Check for data exfiltration
8. Identify initial vulnerability

**Remediation**:
9. Patch vulnerability allowing upload
10. Implement upload restrictions (file types, size, location)
11. Add file integrity monitoring
12. Review all recent uploads

## Open Redirection

### What is Open Redirection?

A vulnerability where a website redirects users to a different URL without proper validation, allowing attackers to redirect to malicious sites.

### Example Malicious URL

```
http://example.com/vulnerable_redirect.php?url=http://malicious.com
```

### Impact

- Phishing attacks
- Malware distribution
- Social engineering attacks
- Reputation damage
- Legal and regulatory consequences

### Types of Open Redirection

- URL-based (most common)
- JavaScript-based
- Meta refresh-based
- Header-based (Location header)
- Parameter-based

## Web Attack Analysis Techniques

### Critical Analysis Principles

**1. Examine ALL User Input (CRITICAL)**

Analysts must check **ALL areas** of web request that originate from user, not just form fields:
- Query parameters
- POST data
- HTTP headers (especially User-Agent, Referer, Cookie)
- File uploads
- JSON/XML request bodies

**Example**: Attackers often inject malicious code into User-Agent header, which analysts may overlook if only checking URL parameters.

**2. Payload and Encoding Analysis**

**Base64 Encoding (MITRE ATT&CK T1027)**:
- Attackers use Base64 to obfuscate malicious information
- Commonly used for web shell communication
- **Tool**: CyberChef for decoding

**Detection**:
- Look for Base64 patterns in request/response
- Check for `base64_decode` functions in web shell code
- Decode suspicious strings to reveal C2 infrastructure

**3. Process Monitoring (Command Injection)**

**If command injection successful, check running processes**:

**Linux (Apache)**:
- Web server process spawns suspicious child process
- Look for: `sh`, `bash`, `/bin/sh`
- Parent process: `apache2`, `httpd`, `nginx`

**Windows (IIS)**:
- Web server process spawns command shells
- Look for: `cmd.exe`, `powershell.exe`
- Parent process: `w3wp.exe`, `inetinfo.exe`

**Red Flag**: Web application process should NOT spawn shell processes under normal operation.

**4. Assessing Attack Success (SQL Injection)**

**Challenge**: Difficult to determine success without HTTP response access.

**Workaround - HTTP Response Size Analysis**:
- Failed SQLi: Consistent small response size (e.g., 486 bytes)
- Successful SQLi: Noticeable difference in response size
- **Pattern**: Multiple requests with size ~500 bytes, then one with 5000+ bytes = likely successful

**Response Code Analysis**:
- 200 + large response = potential data exfiltration
- 200 + normal size = likely failed
- 500 errors = query caused server error (still concerning)

**5. Identifying Automated Attacks**

**Indicators of automated vulnerability scanners**:

**Request Volume**:
- More than 50 requests in 1 second
- Hundreds of requests in few minutes
- Sequential request patterns

**Request Complexity**:
- Complex payloads with multiple attack vectors
- Payloads containing tool signatures
- Systematic variation of parameters

**User-Agent**:
- Tool names: sqlmap, nikto, nessus, burp, OWASP ZAP
- Scripting languages: python-requests, curl
- Missing or generic User-Agent

**Sequential Patterns**:
- Testing each parameter individually
- Incrementing values (id=1, id=2, id=3)
- Alphabetical testing

## General Investigation Best Practices

### For All Web Attacks

1. **Examine ALL fields**: Attacks can occur in any parameter, header, or input field - including HTTP headers like User-Agent
2. **Look for URL encoding**: % symbols indicate encoded special characters - decode for analysis
3. **Check request frequency**: High request rates (>50 req/sec) indicate automated tools
4. **Analyze User-Agent**: Can reveal automated scanners and tool names
5. **Look for patterns**: Sequential values, repeated payloads, timing patterns
6. **Compare response sizes**: Significant differences can indicate successful exploitation
7. **Check response codes**: 200 (success), 302 (redirect), 400s (client errors), 500s (server errors)
8. **Monitor processes**: Web servers should not spawn shell processes (sh, bash, cmd, powershell)
9. **Decode obfuscation**: Base64, URL encoding, hex encoding - use CyberChef

### Determining Attack Success

Without HTTP response content (which is rarely logged):

- **Response size analysis**: Unusual or varying sizes may indicate successful attack
- **Response code analysis**: 200 usually means success, 302/400s often mean failure
- **Pattern analysis**: Successful attacks often followed by different behavior (escalation, lateral movement)
- **Log correlation**: Check for suspicious follow-up activity from same source

### SOC Analyst Notes

- **Proxy Traffic**: When analyzing traffic from proxy servers, remember the source IP belongs to the proxy, not the actual client. Find the real source IP from proxy logs.
- **URL Decoding**: Use URL decoder tools carefully - never upload sensitive access logs to 3rd party services
- **False Positives**: Penetration tests and attack simulation products can trigger alerts - check for scheduled tests
