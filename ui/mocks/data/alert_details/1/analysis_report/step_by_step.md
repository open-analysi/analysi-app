# 1. Alert Overview

- **Alert Description:** Possible CVE-2022-41082 exploitation, known as ProxyNotShell
- **Rule ID:** SOC175
- **Severity:** High
- **Target:** Exchange Server
- **Date:** September 30, 2022

&nbsp;

# 2. Initial Assessment

- **Review Alert Details:**
  - **Hostname:** Exchange Server 2
  - **Suspicious URL:** Contains "PowerShell" and attempts to access \`autodiscover.json\` with \`attacker.example\`
- **Source IP Address:** \`91.234.56.6\`
  - **Geolocation:** South Korea
  - **Reputation:** Known for SSH brute force attacks, listed as malicious in multiple threat intelligence sources

&nbsp;

# 3. Log Retrieval & Analysis

- **Filter Network Logs:**

  - **Search for IP:** 91.234.56.6 in log management tools
  - **Findings:** Three blocked requests on September 30th attempting to exploit Exchange Server 2

- **Verify Email Logs:**
  - **Mailbox Check:** No emails received in September 2022, suggesting no internal phishing attempts

&nbsp;

# 4. External Threat Intelligence

- **VirusTotal & Other Sources:**
  - **Findings:** Two malware and malicious detections
  - **Community Reports:** IP associated with SSH brute force and scanning activities

&nbsp;

# 5. Endpoint and Network Security Verification

- **Check Endpoint Security:**

  - **Tools Needed:** Log management and endpoint security solutions
  - **Findings:** No unusual commands or processes detected on Exchange Server 2 (using EDR)

- **Verify Perimeter Firewall:**
  - **Status:** All suspicious activity blocked
  - **No Further Action Required:** Due to successful blocking

&nbsp;

# 6. Incident Classification & Response

- **Determine Impact:**
  - **Status:** Alert is a true positive; however, the attack was unsuccessful due to perimeter blocking
  - **Action Taken:** No escalation required as the threat was mitigated at the perimeter

&nbsp;

# 7. Recommendations and Mitigation

- **Mitigation Steps:**

  - **Apply Mitigations for CVE-2022-41082:** Until official patches are released, apply recommended mitigations as per Unit 42 and Bleeping Computer articles
  - **Educate Exchange Administrators:** On the risks of web browsing on critical servers

- **Long-term Actions:**
  - **Geo-blocking:** Consider blocking high-risk countries if not conducting business there
  - **Review Firewall Rules:** Ensure they are updated and capable of blocking similar attempts

&nbsp;

# 8. Documentation & Closure

- **Case Documentation:**

  - Record all findings, including IP addresses, logs, and threat intelligence details
  - Note the successful blocking of malicious attempts

- **Close Incident:**
  - Mark as True Positive (Malicious) - Blocked/Prevented
  - Document all steps and findings for future reference and audits

&nbsp;

# Editor's Note

- **Recommendation:** Continue monitoring for similar attempts and ensure all mitigation steps are in place until official patches are released.
