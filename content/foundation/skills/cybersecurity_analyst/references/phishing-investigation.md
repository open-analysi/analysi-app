# Phishing Investigation Reference

## Overview

Phishing is a major threat to organizations. This guide provides structured investigation procedures for analyzing phishing emails and determining appropriate response actions.

## Email Spoofing

### What is Spoofing?

Emails lack mandatory authentication mechanisms, allowing attackers to send emails impersonating others. Attackers use spoofing to make users believe incoming emails are reliable.

### Anti-Spoofing Protocols

- **SPF (Sender Policy Framework)**: Verifies sender's IP is authorized
- **DKIM (DomainKeys Identified Mail)**: Email signature authentication
- **DMARC**: Policy framework for SPF/DKIM

**Note**: Use of these protocols is not mandatory and can cause problems in some cases. Some email programs check automatically, but manual verification is recommended.

### Manual Spoofing Detection

1. Identify SMTP address of the email
2. Use tools like **Mxtoolbox** to obtain domain's SPF, DKIM, DMARC, and MX records
3. Compare SMTP address with authorized mail servers
4. For large institutions with own mail servers, check Whois records of SMTP IP

**IMPORTANT**: Even if sender's address is not spoofed, email may still be malicious. Accounts can be compromised and used to send harmful emails from trusted addresses.

## Email Traffic Analysis

### Key Parameters for Investigation

Search mail gateway for:
- **Sender Address**: e.g., info@companyxyz.io
- **SMTP IP Address**: e.g., 127.0.0.1
- **Domain**: e.g., @companyxyz.io (domain base)
- **Partial domain**: e.g., "companyxyz" (attacker may use Gmail, Hotmail variants)
- **Subject**: May remain constant when sender/SMTP constantly changes

### Analysis Requirements

- Email numbers
- Recipients' addresses
- Time information

**Red flag**: Malicious emails constantly forwarding to same users may indicate:
- Email addresses leaked
- Addresses shared on sites like PasteBin
- Targeted attack

**Note**: Attackers use tools like Harvester (Kali Linux) to find email addresses. Avoid posting personal email addresses on websites.

## Phishing Investigation Questions

### 1. Was Email Sent from Correct SMTP Server?

**Investigation steps**:
1. Check "sender" field to see sending domain
2. Check "Received" field to see email path and source IP
3. Query MX servers for the sender domain using **mxtoolbox.com**
4. Compare actual SMTP IP with authorized MX servers

**Example**:
- Sender: info@companyxyz.io
- Received from: 101.99.94.116 (emkei.cz)
- MX lookup: companyxyz.io uses Google mail servers
- **Conclusion**: No relation between emkei.cz/101.99.94.116 and Google = **SPOOFED**

### 2. Are "From" and "Return-Path/Reply-To" the Same?

**Expected**: Sender and reply recipient should be the same (except exceptional cases)

**Common phishing technique**:
- "From" field: Fake email address or spoofed trusted address
- "Reply-To" field: Real employee's email at legitimate company
- Purpose: Hide fake address when victim replies

**Example attack**:
- Attacker sends email from Gmail/Hotmail with surname matching Google employee
- Claims to be from Google, requests payment for invoice
- Inserts real Google employee email in "Reply-To" field
- When victim replies, message goes to real Google employee, hiding the fake sender

**IMPORTANT**: Different "From" and "Reply-To" doesn't always mean phishing, but requires investigation of:
- Email content
- Attachments
- URLs
- Overall context

## Email Header Analysis

### Critical Email Header Fields

**From**
- Name and email address of sender

**To**
- Recipient details including name and email
- Includes CC (carbon copy) and BCC (blind carbon copy)

**Date**
- Timestamp when email was sent
- Format (Gmail): day dd month yyyy hh:mm:ss
- Example: Wed, 16 Nov 2021 16:57:23

**Subject**
- Topic/summary of message

**Return-Path**
- Where bounced emails are sent when delivery fails

**Domain Key and DKIM Signatures**
- Email signatures for authentication (similar to SPF)

**Message-ID**
- Unique combination of letters/numbers identifying each email
- No two emails have same Message-ID

**MIME-Version**
- Multipurpose Internet Mail Extensions
- Converts non-text content (images, videos) to text for SMTP transmission

**Received**
- Lists each mail server email passed through before reaching inbox
- **Listed in reverse chronological order**:
  - Top = last server
  - Bottom = originating server
- Critical for tracing email path

**X-Spam Status**
- Spam score of email
- Shows if classified as spam
- Displays spam score vs. threshold

### How to Access Email Headers

**Gmail**:
1. Open email
2. Click 3 dots at top right (...)
3. Click "Download message" button

## Static Analysis for Emails

### HTML Email Analysis

Attackers use HTML to hide malicious URLs behind harmless-looking buttons or text.

**VirusTotal URL Analysis - CRITICAL WARNING**:
- Check if URL was previously scanned
- Check **scan date** - old scans may be misleading
- **Attack technique**: Attacker scans clean domain before adding malicious content
- Result: Old VirusTotal scan shows "clean" but current state is malicious
- **Action**: Re-scan using blue arrow button to get fresh results

### SMTP IP Reputation Check

**Tools for IP reputation**:
- **Cisco Talos Intelligence**: Check IP reputation and blacklist status
- **VirusTotal**: Check if IP involved in past malicious activity
- **AbuseIPDB**: Check abuse reports for IP

**Blacklisted SMTP**: May indicate attack carried out on compromised server

### URL Parameter Analysis

**Before clicking links, check for information leakage in URL**:

Example: `popularshoppingsite.com?email=user@example.com`

**Risk**: Even without entering password, attacker knows:
- User email is valid
- User clicked the link
- User can be targeted in future social engineering

**Action**: Change information (like email addresses) before accessing websites in investigation

## Dynamic Analysis

### URL/File Analysis in Sandbox

**Purpose**: Check URLs and files safely without risking infection

### Online Web Browsers

**Example**: Browserling

**Advantages**:
- Not burdened by zero-day vulnerabilities
- Safe browsing from isolation

**Disadvantages**:
- Cannot run downloaded files
- May interrupt analysis

### Sandbox Services

**Commonly used sandboxes**:
- VMRay
- Cuckoo Sandbox
- JoeSandbox
- AnyRun
- Hybrid Analysis (Falcon Sandbox)

**IMPORTANT**: No URLs/files in email doesn't mean it's not malicious. Attacker may send malware as image to avoid detection.

## Additional Phishing Techniques

### Using Legitimate Services

**1. Cloud Storage Services**
- Google Drive / Microsoft OneDrive links
- Appear harmless, trick users into downloading malicious files

**2. Free Subdomain Services**
- Microsoft, WordPress, Blogspot, Wix
- Example: malicious.wordpress.com
- **Deception**: Whois shows "WordPress" or "Microsoft" as owner
- Analysts may believe addresses belong to legitimate institutions

**3. Form Applications**
- Google Forms, Microsoft Forms
- Free form creation services
- Domain is legitimate (google.com)
- Bypasses antivirus software
- Whois shows Google, misleading analysts

## Email Analysis Runbook

### Initial Information Gathering

**Questions to answer**:
1. When was it sent?
2. What is the email's SMTP address?
3. What is the sender address?
4. What is the recipient address?
5. Is the mail content suspicious?
6. Are there any attachments?

### Investigation Workflow (SOC Alert Example)

**Step-by-step process**:
1. **Check the email** - Review headers and content
2. **Get attachment** - Download for analysis (if present)
3. **Check attachment using VirusTotal** - Verify malicious nature
4. **Get any C2 IPs** - Extract command & control addresses
5. **Check if internal devices accessed IPs** - Search firewall/proxy logs
6. **Go to Email solution and delete email if needed** - Remove from other inboxes
7. **Go to EDR solution and confine endpoint if needed** - Isolate compromised systems
   - Check command history for suspicious activity

## Investigation Best Practices

### SMTP Server Verification

1. Extract sender domain from "From" field
2. Extract actual SMTP IP from "Received" field
3. Query legitimate MX servers for sender domain
4. Compare actual SMTP with legitimate servers
5. Check Whois for SMTP IP ownership

### Content Analysis

1. Check for HTML obfuscation of URLs
2. Verify all URLs in VirusTotal (check scan dates!)
3. Look for URL parameters that leak information
4. Examine attachments (hashes, file types)
5. Check for urgency/pressure tactics in content

### Indicator Collection

**Collect and document**:
- Sender email address
- SMTP IP address
- Sending domain
- Reply-To address (if different)
- URLs in email
- Attachment hashes
- C2 domains/IPs
- Recipient list
- Timestamps

### Response Actions

**Based on findings**:
- **True Positive**: Delete emails, isolate endpoints, block IPs/domains
- **Compromised Account**: Reset credentials, check for unauthorized access
- **Mass Campaign**: Check mail gateway for all recipients, delete proactively
- **False Positive**: Document and tune email filters

## Common Red Flags

- Mismatch between "From" and "Reply-To"
- SMTP IP not in authorized MX servers
- SPF/DKIM/DMARC failures
- Old VirusTotal scans showing "clean"
- Blacklisted SMTP IP
- URLs with information-leaking parameters
- Free subdomain services for official communication
- Google Drive/OneDrive links from unknown senders
- Urgency/pressure tactics in content
- Requests for credentials or financial transactions
- Grammar/spelling errors in official communications
