# Network Traffic Analysis Reference

## Overview

Network traffic analysis is critical for understanding Command and Control (C2) communications, data exfiltration, and lateral movement. This guide covers investigation techniques for suspicious network activity.

## Data Sources and Artifacts

### Network Monitoring Systems

**IDS/IPS (Intrusion Detection/Prevention Systems)**
- Monitor network traffic for suspicious activity
- Alert on known attack patterns
- Block malicious traffic (IPS only)

**SIEM (Security Information and Event Management)**
- Aggregates logs from multiple sources
- Correlates events across systems
- Generates alerts based on rules

**Firewall Logs**
- Track inbound and outbound connections
- Show allowed vs blocked traffic
- Critical for checking if security defenses blocked communication
- Cloud firewall logs available for cloud-based systems

### Packet Captures (Pcaps)

**What are Pcaps**:
- Complete network traffic captures
- Contain full packet contents (headers + data)
- Can be downloaded from analysis platforms

**Analysis Tools**:
- **Wireshark**: Deep packet inspection, protocol analysis
- **tcpdump**: Command-line packet capture and analysis
- **NetworkMiner**: Extract files and credentials from pcaps

**Use Cases**:
- Detailed protocol analysis
- Extracting transferred files
- Identifying C2 communication patterns
- Analyzing encrypted traffic metadata

### EDR (Endpoint Detection and Response)

**Network Visibility from EDR**:
- Browsing history
- Recently executed processes with network activity
- Active network connections
- DNS queries from endpoint
- Downloaded files

## Investigation Workflow for Suspicious Communication

### Phase 1: Define "Who" and "Where"

**Document full information for systems involved**:

**Source Information**:
- Source IP address
- Source hostname
- Source domain (if applicable)
- User accessing the system at time of event
- System role/criticality

**Destination Information**:
- Destination IP address
- Destination hostname
- Destination domain
- Service/application running on destination
- Geographic location (for external IPs)

**Connection Details**:
- Ports involved (source and destination)
- Protocol (TCP, UDP, ICMP)
- Timestamp of communication
- Duration of connection
- Volume of data transferred

### Phase 2: Scope the Threat

**Alert Grouping**:
- If same entity triggers multiple alerts, group into one incident
- Avoid investigating each alert separately
- Create unified timeline of activity

**Large-Scale Activity**:
- If hundreds of systems involved, don't document all immediately
- Focus on confirming actual infection first
- Sample representative systems for investigation
- Expand documentation if confirmed malicious

**Pattern Recognition**:
- Is this isolated or part of larger campaign?
- Are other systems showing similar behavior?
- Check for common IOCs across alerts

### Phase 3: Determine Traffic Direction and Context

**Traffic Direction Types**:

**Internal-to-Remote (Most Suspicious)**:
- Internal system connecting to external IP
- Primary indicator of C2 communication or data exfiltration
- Requires immediate investigation

**Internal-to-Internal**:
- Communication between internal systems
- Often benign (backups, file shares, monitoring)
- **Context matters**: Time of day, systems involved, normal baseline

**Remote-to-Internal (Inbound)**:
- External system connecting to internal IP
- Could be legitimate (users, partners, customers)
- Or malicious (scanning, exploitation attempts)

**C2 Traffic Context**:
- Internal-to-internal C2 = likely benign (e.g., backup servers)
- Internal-to-remote C2 = highly suspicious
- Check if "remote" IP is actually internal proxy/NAT

### Phase 4: Reputation and Anomaly Analysis

**IP/Domain Reputation Checks**:

**Threat Intelligence Sources**:
- VirusTotal
- AbuseIPDB
- Cisco Talos
- AlienVault OTX
- ThreatCrowd
- Shodan (for infrastructure info)

**What to Look For**:
- Blacklist status
- Associated malware families
- Reported malicious activity
- Hosting provider (bulletproof hosting?)
- Country of origin
- Domain registration date (newly registered = suspicious)

**Port and Service Anomalies**:

**Non-Standard Ports**:
- HTTP traffic on port 8080, 8888, or random high ports
- HTTPS on port 8443 or non-443 ports
- SSH on non-22 ports
- RDP on non-3389 ports

**Why Anomalous**:
- Attackers use non-standard ports to evade detection
- May indicate tunneling or proxy usage
- Could be C2 over unusual protocols

**Document**:
- Expected port for protocol
- Actual port used
- Why this is significant

### Phase 5: Assess Intent and Tools

**Suspicious Web Requests**:

**Command Examples**:
```bash
which nc       # Looking for netcat
which curl     # Looking for download tools
which wget     # Looking for download tools
which python   # Looking for scripting
which gcc      # Looking for compilation
```

**What This Indicates**:
- Attacker checking available tools on system
- Preparing for data transfer or remote access
- Reconnaissance of system capabilities

**Tool Identification in Traffic**:
- User-Agent headers revealing tools (curl, wget, python-requests)
- Known C2 framework patterns (Cobalt Strike, Metasploit)
- Encoded command patterns

### Phase 6: Covering Tracks Detection

**Log Deletion Indicators**:

**Linux Systems**:
- Check for deletion of `/var/log/apache2/*`
- Check for deletion of `/var/log/auth.log`
- Look for `rm -rf` commands in command history
- Check for cleared bash history

**Windows Systems**:
- Event log clearing (Event ID 1102)
- Deletion of IIS logs
- Timestomping (modified file timestamps)

**Detection Methods**:
- Timeline gaps in logs
- Sudden appearance of new, empty log files
- Logs with recent creation date but old "last modified"
- EDR detecting log file manipulation

## Advanced Techniques for Persistent Threats

### Beaconing Detection

**What is Beaconing**:
- Compromised systems periodically connecting to C2 server
- Low-volume, regular intervals
- Evades traditional signature detection

**Detection Methods**:

**1. Statistical Analysis**:
- Calculate time intervals between connections
- Compute standard deviation
- Low standard deviation = regular beaconing pattern
- Example: Connections every 60 seconds ±2 seconds = suspicious

**2. Frequency Analysis**:
```
Connection times:
10:00:00
10:01:00
10:02:00
10:03:00
Pattern: Every 60 seconds = beaconing
```

**3. Connection Characteristics**:
- Small, consistent data transfer sizes
- Same destination IP/domain
- Regular intervals (hourly, every 5 minutes, etc.)
- Connections from internal to external only

**Investigation Focus**:
- Activity from internal hosts to external addresses
- **Any network port** (beaconing not limited to specific ports)
- Temporal patterns (time-series analysis)
- Bandwidth patterns (low, consistent volume)

**Dynamic Analysis for Beaconing**:
- Review pcap files for C2 communication patterns
- Look for periodic, low-volume connections
- Check for jitter (small random delays to evade detection)
- Analyze protocol patterns (HTTP GET every X minutes)

### Traffic Filtering and Defensive Measures

**Proactive Blocking**:

**TOR Exit Nodes**:
- Block inbound connections from known TOR exit nodes
- Prevents anonymous attacker access
- TOR exit node lists publicly available

**Known Malicious Infrastructure**:
- Block IPs/domains from threat intelligence feeds
- Implement DNS sinkholing for known C2 domains
- Use threat intelligence platforms for automated blocking

**Geographic Filtering**:
- Block traffic from countries where no business occurs
- Implement geofencing for sensitive services
- Allow-list known business partner countries

**Protocol/Port Restrictions**:
- Block unnecessary outbound protocols
- Restrict outbound ports to business-required only
- Monitor for protocol tunneling (HTTP over non-80/443)

## Network Analysis Best Practices

### During Investigation

**1. Preserve Evidence**:
- Download pcap files before they expire
- Save firewall logs for incident timeframe
- Screenshot connection details
- Export connection metadata

**2. Correlate Multiple Sources**:
- Check firewall AND proxy AND IDS logs
- Verify endpoint telemetry matches network logs
- Look for gaps (missing logs = potential tampering)

**3. Timeline Construction**:
- Build chronological timeline of network events
- Include first occurrence, duration, last occurrence
- Note any gaps or anomalies in timeline

**4. Baseline Comparison**:
- Compare to normal network patterns
- Check historical data for same system
- Identify deviations from baseline

### Red Flags in Network Traffic

**Immediate Investigation Required**:
- Outbound connections to known C2 infrastructure
- Large outbound data transfers to external IPs
- Connections to newly registered domains
- Traffic to suspicious ports (4444, 8080, 31337)
- Encrypted traffic to unusual destinations
- Regular beaconing patterns
- Traffic to TOR nodes
- Connections immediately after malware alert

**Suspicious but Investigate**:
- High-volume internal-to-internal traffic
- After-hours network activity
- Failed connection attempts to multiple IPs
- DNS queries for random-looking domains
- Traffic from unexpected systems (servers browsing web)

## Common Investigation Mistakes

**1. Ignoring HTTP Headers**:
- User-Agent reveals tools and frameworks
- Referer shows attack path
- Cookie manipulation attempts

**2. Trusting Internal-to-Internal**:
- Lateral movement uses internal connections
- Compromised systems communicating internally
- Always verify legitimacy

**3. Focusing Only on Blocked Traffic**:
- Allowed traffic may be more important
- Successful C2 won't be blocked initially
- Check what got through, not just what was blocked

**4. Missing Encrypted Traffic**:
- HTTPS hides payload but metadata still visible
- Certificate information can be suspicious
- Connection patterns still detectable

**5. Not Checking DNS**:
- DNS queries precede connections
- DGA (Domain Generation Algorithm) patterns
- DNS tunneling for data exfiltration

## Integration with Other Analysis

**Combine Network Analysis with**:

- **log-analysis.md**: Firewall, proxy, DNS log details
- **malware-analysis.md**: C2 infrastructure from malware analysis
- **web-attacks.md**: Web shell communication patterns
- **threat-intelligence.md**: IP/domain reputation enrichment

**Key Correlation Points**:
- Match network connections to process execution
- Link C2 IPs to malware file hashes
- Connect web shell uploads to subsequent network activity
- Correlate beaconing with scheduled tasks or persistence
