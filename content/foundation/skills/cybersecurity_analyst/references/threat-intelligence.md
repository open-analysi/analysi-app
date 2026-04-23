# Cyber Threat Intelligence Reference

## Overview

Cyber Threat Intelligence (CTI) is a cybersecurity discipline that generates actionable output to inform organizations about cyberattacks and minimize damage by processing and interpreting data collected from multiple sources.

### Goal of CTI

Understand the **Techniques, Tactics, and Procedures (TTPs)** of attackers by:
- Collecting data from multiple sources (Indicators of Compromise)
- Processing data to create information
- Matching information to specific organizations
- Producing organization-specific intelligence

## CTI Life Cycle

### 1. Planning

Identifies the purpose, audience, and desired outcomes of intelligence, ensuring scope aligns with organizational needs.

**Key questions to consider**:
- **Does your organization have a SOC team?** Determines whether intelligence should be technical or high-level
- **Has your organization been attacked before? If so, what was the success rate?** Determines how often intelligence will be used and frequency of data collection
- **Do the attacks target the organization or individuals?** Determines focus (External Attack Surface Management or Digital Risk Protection)
- **Are other companies in your industry exposed to the same attacks?** Indicates need for industry-based intelligence

### 2. Information Gathering

Determines internal and external sources for data collection.

**Data sources**:
- Hacker Forums
- Ransomware Blogs
- Deep/Dark Web Forums and Bot Markets
- Public Sandboxes
- Social Media (Telegram/ICQ/IRC/Discord/Twitter/Instagram/Facebook/LinkedIn)
- Surface Web (Cybersecurity Blogs, etc.)
- Public Research Reports
- File Download Sites
- Code Repositories (Github/Gitlab/Bitbucket, etc.)
- Public Buckets (Amazon S3/Azure Blob, etc.)
- Search Engines (Shodan/Binary Edge/Zoomeye, etc.)
- IOC Sources (Alienvault, Abuse.ch, MalwareBazaar, etc.)
- Honeypots
- SIEM, IDS/IPS, Firewalls
- Public Leak Databases

### 3. Processing

Data is filtered to remove false positives and correlated to extract necessary information.

### 4. Analysis and Production

Information is interpreted and analyzed to produce consumable intelligence, which is then used to prepare reports.

### 5. Dissemination and Feedback

Intelligence is distributed to the intended recipient through appropriate channels. Feedback is provided to improve intelligence quality and reduce false positives.

**Example**: If a subdomain is marked as suspicious but should not be, feedback is needed to improve the intelligence.

## Extended Threat Intelligence (XTI)

XTI is the next-generation threat intelligence that addresses inadequacies of classical CTI models.

**Key difference**: XTI creates an attack surface belonging to the organization to produce organization-specific intelligence, giving visibility into assets and what to defend.

**XTI Components**:
1. External Attack Surface Management (EASM)
2. Digital Risk Protection (DRP)
3. Cyber Threat Intelligence (CTI)

## Determining the Attack Surface

Proactively examine your attack surface as exposed from the internet to decide how to better protect exposed assets.

### Attack Surface Includes

- Domains
- Subdomains
- Websites
- Other related assets

### Discovery Process

1. Start with primary domain provided by organization
2. Create entire entity structure over this domain
3. Find other domains using services like host.io (domains that redirect to main domain)
4. Verify ownership using whois outputs or content analysis

**Tools for further analysis**: Shodan, VirusTotal, BinaryEdge, Zoomeye, Censys

## Key Intelligence Sources

### Shodan

Web-based server search engine for finding systems open to the internet with specific filters.

**Use cases**:
- Detect all systems of a specific country or organization with specific open ports
- Identify internet-exposed services and vulnerabilities

**Alternatives**: BinaryEdge, Zoomeye, Censys

### Resources Providing IOCs

Collecting IPs, domains, hashes, and C2s is critical to protect from potential attacks.

**Key IOC sources**:
- Alienvault
- Malwarebazaar
- Abuse.ch
- Malshare
- Anyrun
- VirusTotal
- Hybrid-Analysis
- Totalhash
- Phishunt
- Spamhaus
- Tor Exit Nodes
- Urlscan
- Zone-h
- And many more

**Best practice**: Maintain wide list of sources and pull data via API as often as possible. Use whitelisting and other data elimination methods to reach lowest false positive rate.

### Hacker Forums

One of the most important places to gather intelligence. Threat actors usually share information in hacker forums first when preparing for an attack.

**Intelligence gathered**:
- Direction of the attack
- Targets
- Methods to be used in the attack
- Who is behind the attack
- Sales of access to hacked systems

**Action when compromised**: Close access to systems, determine root cause, prevent access by more dangerous actors.

### Ransomware Blogs

Gained popularity starting with Covid-19 pandemic (2020+). Ransomware groups post data of victims who refused to pay on their blogs.

**Intelligence gathered**:
- Which organization is targeted by which group
- Which groups target which countries
- Motivations of ransomware groups
- Announcements and TTPs

**Popular ransomware groups**: Lockbit, Conti, Revil, Hive, Babuk

### Black Markets

Systematized versions of "Selling" categories in hacker forums.

**Items sold**:
- Credit cards
- Stealer logs
- RDP accesses
- Prepaid accounts

**Note**: Limited information on its own, but produces actionable output when matched to attack surface.

### Chatters (Instant Messaging Platforms)

Platforms for bilateral or multiple written and audio-visual communications.

**Popular platforms used by threat actors**:
- Telegram
- ICQ
- IRC
- Discord

**Intelligence gathered**: Sensitive data shared during communications, information about attack preparation, sales of credit cards/accounts/access.

### Code Repositories

Full of sensitive data forgotten by organizations or individual users.

**Common leaked data**:
- Database access information
- Login credentials
- Sensitive configuration files
- Secret API keys
- Exploit code for new vulnerabilities

**Popular repositories**: Github, Gitlab, Bitbucket

**Search technique**: Use specific parameters (e.g., "password" "example.com")

### File Share Websites

Used by threat actors to share files anonymously. Files may belong to organizations and can be leaked in case of breach.

**Data extraction methods**:
1. Using guessing algorithm to detect unique keys (costly)
2. Using Dork queries to capture indexed files (simpler, low-cost)

### Public Buckets

Cloud-based data storage environments (Amazon S3, Azure Blob, Google Cloud Storage) that are misconfigured and publicly accessible.

**Threat**: Brute force attacks using wordlists containing organization names can uncover public buckets and endpoints, exposing sensitive data.

### Honeypots

Systems with security vulnerabilities designed to attract and trap attackers.

**Use**: Collect IOCs like attacker IPs

**Popular honeypots**: Kippo, Cowrite, Glastopf

### SIEM/IDS/IPS/Firewalls

Hundreds of daily attacks on an institution can be prevented by security product rules.

**Intelligence source**: Filter logs to identify attacker IPs and malicious file hashes.

## Using Threat Intelligence

After data is interpreted in relation to the attack surface, it becomes consumable threat intelligence for three areas:

### 1. External Attack Surface Management (EASM)

Monitors organization's external assets and detects security vulnerabilities by continuously monitoring assets and using threat intelligence.

**Alert Examples**:

- **New Digital Asset(s) Detected**: Check if asset belongs to organization and was created by authorized users
- **Domain Information Change Detected**: Verify if change was made by authorized users
- **DNS Information Change Detected**: Verify authorization and check for malicious intent
- **Internal IP Address Detected**: Investigate exposure of internal IP in A record
- **Critical Open Port Detected**: Investigate if port is actively used by network
- **SSL Certificate Revoked/Expired**: Critical - leads to insecure communication
- **Suspicious Website Redirection**: Domain redirects to website not in asset list - potential breach
- **Vulnerability Detected**: Severity depends on source and details of vulnerability

### 2. Digital Risk Protection (DRP)

Majority of XTI's intelligence, derived from data mapped to attack surface.

**Encompasses**:
- Brand reputation
- Deep & Dark Web threats
- Bank fraud protection
- Supply chain risks
- Web surface threats
- Executive protection

**Alert Examples and Actions**:

- **Potential Phishing Domain Detected**: Investigate safely; contact registrar/ISP for takedown if mimicking
- **Rogue Mobile Application Detected**: Analyze APKs safely; take down copycat apps if malicious
- **IP Address Reputation Loss**: Investigate blacklisting/IOC feeds/torrent activity; eliminate root cause
- **Impersonating Social Media Account**: Review and request closure if fraudulent
- **Botnet Detected at Black Market**: Reset user password (customer) or conduct forensic investigation (employee)
- **Suspicious Content Detected at Deep & Dark Web**: Analyze and take necessary action
- **Suspicious Content Detected at IM Platforms**: Analyze context and take action if threat exists
- **Stolen Credit Card Detected**: Inform fraud teams and cancel card
- **Data Leak Detected on Code Repository**: Delete if managed by us; otherwise pursue takedown
- **Company Related Information Detected on Malware Analysis Services**: Investigate and analyze file
- **Employee and VIP Credential Detected**: Reset passwords quickly

### 3. Cyber Threat Intelligence (CTI)

Sub-branch of XTI providing awareness of general cyber world activities.

**Intelligence gathered**:
- Current malicious campaigns
- Orientation of ransomware groups
- Offensive IP addresses around the world

**Best practice**: Support CTI with corporate feeds for most efficient intelligence. Integrate CTI feeds into SIEM, SOAR, and EDR tools for better protection.

## Best Practices

1. **Maintain wide source list**: Pull data from as many sources as possible
2. **Use APIs**: Almost all IOC sources provide data via API
3. **Implement data elimination**: Use whitelisting to reduce false positives
4. **Correlate with attack surface**: Match collected data to attack surface for actionable output
5. **Continuous monitoring**: CTI is constantly changing and evolving field
6. **Provide feedback**: Improve intelligence quality by reporting false positives
7. **Integrate with security tools**: Use intelligence feeds in SIEM, SOAR, EDR
8. **Monitor regularly**: Keep ahead of threats by staying current with intelligence sources
