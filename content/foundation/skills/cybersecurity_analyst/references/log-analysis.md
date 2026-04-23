# Network Log Analysis Reference

This guide provides essential information for analyzing various network log types during security investigations.

## Netflow Log Analysis

### What is Netflow?

Netflow is a network protocol that collects IP traffic information. Although developed by Cisco, many manufacturers support Netflow or similar protocols (Sflow, etc.).

### Netflow Use Cases

- ISPs can bill for services
- Network design and analysis
- Network monitoring (top sources generating traffic, most used ports, etc.)
- Service quality measurement
- **SOC analysis for anomaly detection**

### Flow Definition

**Flow**: The set of packets that make up communication between source and destination.

### Information Collected for Flow

- Source IP Address
- Destination IP Address
- Source Port (UDP and TCP only)
- Destination Port (UDP and TCP only)
- IP Protocol
- Interface Information
- IP Version Information

### Detectable Activities via Netflow

- Abnormal traffic volume increases
- Data leaks
- Access to private systems
- New IPs in the network
- Systems accessed for the first time
- Command and Control / beaconing activity

## Firewall Log Analysis

### Overview

Firewalls manage incoming and outgoing network packets based on predetermined security rules. Modern firewalls (NGFWs) can identify applications and content at OSI Layer-7, not just Layer-3 packet routing.

### Key Firewall Log Fields

**Sample log snippet**:
```
date=2022-05-21 time=14:06:38
srcip=172.14.14.26 srcport=50495 srcintf="ACC-LAN"
dstip=142.250.186.142 dstport=443 dstintf="Wan"
srccountry="Reserved" dstcountry="United States"
action="accept" service="HTTPS"
sentbyte=2518 rcvdbyte=49503 sentpkt=13 rcvdpkt=42
```

### Important Fields

- **srcip**: Source IP Address
- **srcport**: Source Port
- **srcintf/srcintfrole**: Source Interface and Role
- **dstip**: Destination IP Address
- **dstport**: Destination Port
- **dstintf/dstintfrole**: Destination Interface and Role
- **action**: Action taken (accept, deny, drop, close, client-rst, server-rst)
- **service**: Service information
- **transip**: NAT IP (internal to external mapping)
- **sentbyte/rcvdbyte**: Bytes sent/received
- **sentpkt/rcvdpkt**: Packets sent/received

### Action Types

- **accept**: Packet passed successfully
- **deny**: Packet blocked, information returned to source about block
- **drop**: Packet blocked, NO information returned to source
- **close**: Communication mutually terminated
- **client-rst**: Communication terminated by client
- **server-rst**: Communication terminated by server

### Analysis Priorities

1. Check IP and port information first
2. Check "action" field to see if traffic reached target
3. Filter by source and destination IP addresses for easier analysis

### Detectable Activities

- Port-Scan activities
- Communication with IoCs (Indicators of Compromise)
- Lateral (lan-lan) or vertical (lan-wan, wan-lan) unauthorized access
- Cross-reference with IPS alerts (e.g., was attack that IPS denied actually accepted by firewall?)

## VPN Log Analysis

### Overview

VPN allows connection to a local network remotely. VPN is an indispensable access type for enterprise networks and a common entry point for attackers.

### Key VPN Log Fields

**Sample log snippet**:
```
date=2022-05-21 time=14:06:38
logid="0101039424" type="event" subtype="vpn"
action="tunnel-up" tunneltype="ssl-web"
remip=13.29.5.4 user="jdoe"
reason="login successfully" msg="SSL tunnel established"
```

### Important Fields

- **remip**: IP address that established VPN connection
- **user**: User information
- **reason**: VPN connection request result
- **tunnelip**: IP assigned for VPN access (may be in separate log)
- **action**: Action taken (tunnel-up, tunnel-down, etc.)

### Analysis Focus

- IP address making the connection
- Which user connected
- Result of access request (successful/failed)
- **Note**: After successful VPN connection, firewall traffic logs will show "tunnelip" as source IP for user's network activities

### Detectable Activities

- Successful/Unsuccessful VPN accesses
- Brute-force attacks against VPN accounts
- VPN accesses from outside specified countries
- VPN accesses outside specified time periods

## Proxy Log Analysis

### Overview

Proxy acts as bridge between endpoint and internet. Organizations use proxies for internet speed, centralized control, and increased security.

### Proxy Types

- **Transparent Proxy**: Target server can see real source IP
- **Anonymous Proxy**: Target server cannot see real source IP (sees proxy IP instead)

### Key Proxy Log Fields

**Sample log snippet**:
```
date=2022-05-21 time=16:15:44 type="utm" subtype="webfilter"
srcip=192.168.209.142 srcport=34280
dstip=54.20.21.189 dstport=443
hostname="android.prod.cloud.netflix.com"
action="blocked"
url="https://android.prod.cloud.netflix.com/"
urlsource="Local URLfilter Block"
msg="URL was blocked because it is in the URL filter list"
```

### Important Fields

- **hostname**: Requested domain
- **url**: URL address requested
- **action**: Action information (blocked, allowed)
- **urlsource**: URL source list
- **profile**: Source profile applied

### CRITICAL NOTE for SOC Analysts

**When analyzing traffic from Proxy servers, the source IP belongs to the proxy, not the actual client. You MUST find the real source IP from proxy logs to continue analysis.**

### Detectable Activities

- Connections to/from suspicious URLs
- Infected system detection
- Detection of tunneling activities

## IDS/IPS Log Analysis

### IDS vs IPS

- **IPS** (Intrusion Prevention System): Detects AND prevents suspicious activities
- **IDS** (Intrusion Detection System): Only detects suspicious activities

Both use signature databases to detect known attacks. Same device/product, different actions based on signature configuration.

### Key IDS/IPS Log Fields

**Sample log snippet**:
```
date=2022-05-21 time=14:06:38
type="utm" subtype="ips" level="alert" severity="high"
srcip=12.11.2.4 srccountry="Reserved"
dstip=19.66.201.16 dstcountry="United States"
action="detected" proto=17 service="DNS"
attack="DNS.Server.Label.Buffer.Overflow"
srcport=57673 dstport=53 direction="incoming"
attackid=37088 msg="misc: DNS.Server.Label.Buffer.Overflow"
```

### Important Fields

- **severity**: Incident severity (low, medium, high, critical)
- **attack**: Attack details
- **action**: Action information (detected, blocked)
- **direction**: Direction of packet (inbound, outbound)
- **attackid**: Attack ID for reference lookup

### Analysis Checklist

1. **Check direction of attack** (inbound or outbound)
2. **Check event severity level** (high and critical = more important, quick action required, less likely FP)
3. **Check for multiple signature triggers** between same source and target (increases severity)
4. **Verify if port/service is running on target** - If yes, raise to critical and check for infection
5. **Check action taken** (detected vs. blocked):
   - If blocked and no other firewall requests: wait and monitor
   - If only detected: review other requests and apply block if not FP

### Detectable Activities

- Port scanning activities
- Vulnerability scans
- Code Injection attacks
- Brute-Force attacks
- DoS/DDoS attacks
- Trojan activities
- Botnet activities

## WAF Log Analysis

### Overview

WAF (Web Application Firewall) secures web-based applications. Often firewall or IDS/IPS alone are insufficient for web-based attack detection.

### SSL Offload

Decryption of SSL-encrypted traffic to make content visible and controllable. WAF without SSL Offloading cannot inspect HTTPS payload effectively.

### Key WAF Log Fields

**Sample log snippet**:
```
date=2022-01-26 time=19:47:26
type=attack main_type="Signature Detection" sub_type="SQL Injection"
severity_level=High proto=tcp service=https/tls1.2
action=Alert src=19.6.150.138 src_port=56334
dst=172.16.10.10 dst_port=443
http_method=get http_url="?v=(SELECT (CHR(113))||..."
http_host="app.example.com"
signature_id="030000136" attack_type="SQL Injection"
```

### Important Fields

- **main_type**: Detection type
- **sub_type**: Detected activity detail
- **severity_level**: Incident severity
- **action**: Action taken (Alert, Block)
- **http_method**: HTTP request method
- **http_url**: URL requested
- **http_agent**: User-agent info
- **attack_type**: Attack type

### Analysis Focus

- Check source and target IP for high severity attacks
- **Check WAF response**: Did WAF block or just alert?
- **Check application response code**:
  - 200 with attack = successful attack reached server
  - 404 = attack failed (not found)
  - Some applications incorrectly return 200 instead of 404 (FP consideration)

### Detectable Activities

- Known web vulnerabilities
- SQL Injection, XSS, Code Injection, Directory Traversal attacks
- Suspicious method usage (PUT, DELETE)
- Top requesting IP addresses
- Most requested URLs

## Web Server Log Analysis

### Overview

Most services are web-based. Most commonly used web servers: Microsoft IIS, Apache, Nginx.

### Sample Web Log

```
71.16.45.142 - - [12/Dec/2021:09:24:42 +0200] "GET /?id=SELECT+*+FROM+users HTTP/1.1" 200 486 "-" "curl/7.72.0"
```

### Log Components

- **Source IP**: 71.16.45.142
- **Date**: 12/Dec/2021:09:24:42 +0200
- **Request Method**: GET
- **Requested URL**: /?id=SELECT+*+FROM+users
- **Version**: HTTP/1.1
- **Server Response**: 200
- **Data Size**: 486 bytes
- **User-Agent**: curl/7.72.0

### HTTP Request Methods

- **GET**: Retrieve data from server
- **POST**: Send data to server (pictures, videos) - *content NOT usually logged by default*
- **DELETE**: Delete data on server
- **PUT**: Send data to server (creates or updates files) - *content NOT usually logged by default*
- **OPTIONS**: Shows which methods server accepts

### HTTP Response Codes

**Common codes**:
- **200 (OK)**: Request successful, response returned
- **301 (Permanent Redirect)**: Redirected to different location
- **403 (Forbidden)**: Access not allowed
- **404 (Not Found)**: Content not found
- **503 (Service Unavailable)**: Server cannot respond

**Categories**:
- 100-199: Informational responses
- 200-299: Successful responses
- 300-399: Redirection messages
- 400-499: Client error responses
- 500-599: Server error responses

### Interpreting Responses for Attack Analysis

**For SQL Injection attack in URL**:
- **200 response**: Attack successful (but check for app glitches that return 200 instead of 404)
- **404 response**: Attack failed (URL not found)
- **500 response**: Attack failed, but caused server error (potential DoS)

### User-Agent Analysis

- **Real user**: "Mozilla", "Chrome", or similar browser info
- **Automated tool**: "nikto", "nessus", "nmap", "curl"
- **WARNING**: User-Agent can be spoofed, always verify

### Detectable Activities

- Web requests with attack vectors (SQL Injection, XSS, Code Injection, Directory Traversal)
- Top requesting IP information
- Most requested URL information
- Most received HTTP response codes
- Suspicious method usage (PUT, DELETE)

## DNS Log Analysis

### Overview

DNS is used for domain-IP resolution. Critical for investigating which domains a system requested and when.

### Two DNS Log Categories

1. **DNS Server Records**: Audit events on server hosting DNS records (adding, deleting, editing records)
2. **DNS Queries**: Actual query logs (must be manually enabled, not kept by default)

### Key DNS Query Log Fields

**Sample log**:
```json
{
  "timestamp": 1591367999.306059,
  "source_ip": "192.168.4.76",
  "source_port": 36844,
  "destination_ip": "192.168.4.1",
  "destination_port": 53,
  "protocol": "udp",
  "query": "testmyids.com",
  "qtype_name": "A"
}
```

### Log Components

- Date-Time
- Querying IP, Port
- Query type
- Requested domain

### Analysis Questions

- Has the system made domain requests to categories it should not access?
- Has the system made requests to risky category domains?
- Were known services (Google Drive, OneDrive) accessed during data leak situations?
- Are there requests to domains from Threat Intelligence resources (IoCs)?
- Is there access to DNS Over TLS (DoT) or DNS over HTTPS (DoH) services?

### Detectable Activities

- First time visited domains
- Domains or subdomains over a certain character size
- Detection of NX (non-existent) returning domains
- Domain IoC controls
- DNS over TLS/HTTPS access detection
- **DNS Tunneling**: Multiple DNS requests to randomly created subdomains in short time period

### Real-World Example

**SolarWinds SUNBURST attack (2020)**: Could have been detected by analyzing DNS logs for anomalous domain requests.

## General Log Analysis Best Practices

### Cross-Correlation

Always correlate findings across multiple log sources:
- Check firewall logs for IPS-denied IPs (was there any accepted traffic?)
- Check firewall/proxy logs for IPs/domains from antivirus alerts
- Use firewall logs to identify other systems communicating with infected system

### Key Analysis Principles

1. **Start with IP and port information**
2. **Check action/result fields** (blocked vs. allowed)
3. **Filter strategically** by source/destination for easier analysis
4. **Look for patterns** (timing, frequency, sequential activity)
5. **Verify security device placement** (is attacked system behind WAF/IPS/Firewall?)
6. **Consider false positives** from penetration tests or security tools
7. **Document findings** with timestamps and evidence

### IOC (Indicator of Compromise)

Evidence that occurs before, during, and after a cybersecurity incident. IOCs are crucial for determining:
- Type of attack
- Tools used during attack
- Possible attacker identity
