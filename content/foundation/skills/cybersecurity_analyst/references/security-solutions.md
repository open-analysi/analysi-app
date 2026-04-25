# Security Solutions Reference

This document provides definitions and key information about common security solutions encountered during security alert investigations.

## Intrusion Detection System (IDS)

An Intrusion Detection System (IDS) is hardware or software used to detect security breaches and attacks by monitoring a network or host.

### Types of IDS

**Network Intrusion Detection System (NIDS)**
Network Intrusion Detection System (NIDS) is used to detect whether there is traffic suitable for attacker behavior by passing all traffic on the network through it. When abnormal behavior is observed in the traffic, an alert can be generated and the administrator can be informed.

**Host Intrusion Detection System (HIDS)**
The Host Intrusion Detection System (HIDS) works on a specific host in the network. It tries to detect malicious activities by examining all network packets coming to this device and all network packets going from this device. Detected malicious behaviors are reported to the administrator as an alert.

**Protocol-Based Intrusion Detection System (PIDS)**
A protocol-Based Intrusion Detection System (PIDS) is a type of IDS that examines the traffic between a server and a client in a protocol-specific way.

**Application Protocol-based Intrusion Detection System (APIDS)**
An Application Protocol-Based Intrusion Detection System (APIDS) is a type of IDS that tries to detect security breaches by monitoring communication in application-specific protocols.

**Hybrid Intrusion Detection System**
A hybrid Intrusion Detection System is a type of IDS in which two or more violation detection approaches are used together.

### IDS Functions

- Detecting security breaches according to the detection methods used by the IDS product is the main task of the IDS product.
- When IDS detects a security breach, the administrator is informed, and/or this information is sent to the SIEM product.

### Popular IDS Products

- Zeek/Bro
- Snort
- Suricata
- Fail2Ban
- OSSEC

### IDS Log Sources

During its operation, IDS detects security violations according to previously established rules. Therefore, it is very important how much the written rule defines the attack. If the written rule cannot detect the attack or detects the normal behavior as an anomaly, the rule should be changed or the incoming alerts should be reviewed by the analyst. Among the IDS logs examined by the analyst, there is information in the network packets regarding the security breach.

## Intrusion Prevention System (IPS)

An Intrusion Prevention System (IPS) is hardware or software that detects security violations by monitoring a network or host and prevents security violations by taking the necessary action.

### Types of IPS

**Network-Based Intrusion Prevention System (NIPS)**
Network-based intrusion prevention system (NIPS) is a type of IPS that detects security violations and eliminates security violations by monitoring all incoming traffic to the network it is in.

**Host-Based Intrusion Prevention System (HIPS)**
Host-based intrusion prevention system (HIPS) is software that monitors and analyzes suspicious activities for a host.

**Network Behavior Analysis (NBA)**
Network Behavior Analysis (NBA) is a type of IPS that detects and blocks unusual traffic flows and Denial of Service (DoS) attacks on the network.

**Wireless Intrusion Prevention System (WIPS)**
A Wireless Intrusion Prevention System (WIPS) is a type of IPS that monitors and analyzes wireless network protocol traffic of wireless devices in a network.

### IPS Functions

IPS is responsible for preventing malicious behavior by detecting security breaches.
It notifies the relevant authorities of the security breach encountered during monitoring as an alert.

### Popular IPS Products

- Cisco NGIPS
- Suricata
- Fidelis

### IPS Log Fields

- Date/Time Information
- Message About the Attack
- Source IP Address
- Source Port
- Destination IP Address
- Destination Port
- Action Information
- Device Name

## Firewall

A firewall is a security software or hardware that monitors incoming and outgoing network traffic according to the rules it contains and allows the passage of network packets or prevents the passage of packets according to the nature of the rule.

### Types of Firewalls

**Application-Level Gateways (Proxy Firewalls)**
Application-Level Gateways (Proxy Firewalls) are a type of firewall that functions at the application layer between two end systems. Unlike basic firewalls, it captures and analyzes packets in the application layer according to the OSI model.

**Circuit-Level Gateways**
Circuit-Level Gateways are a type of firewall that can be easily configured, has low resource consumption, and has a simplified structure. These types of firewalls verify TCP connections and sessions and operate in the session layer of the OSI model.

**Cloud Firewalls**
Cloud Firewalls are the type of firewall used when the institution receives firewall service over the cloud as a service. Another name is "FWaaS" (firewall-as-a-service).

**Endpoint Firewalls**
Endpoint Firewalls are a type of host-based firewall installed on devices. For example, the "Windows Defender Firewall", which comes pre-installed in Windows, is an example of this type of firewall.

**Network Address Translation (NAT) Firewalls**
Network Address Translation (NAT) Firewalls are a type of firewall designed to access internet traffic and block unwanted connections. Such firewalls are used to hide the IP addresses in the internal network from the external network.

**Next-Generation Firewalls (NGFW)**
Next-Generation Firewalls (NGFW) are a type of firewall that combines the features of different firewalls available under the conditions of that day on a single firewall. These firewalls have a deep-packet inspection (DPI) feature. This type of firewall is designed to block external threats, malware attacks, and advanced attack methods.

**Packet-Filtering Firewalls**
Packet-Filtering Firewalls are the most basic type of firewall. It has a feature that monitors network traffic and filters incoming packets according to configured rules.

**Stateful Multi-Layer Inspection (SMLI) Firewalls**
Stateful Multi-Layer Inspection (SMLI) Firewall is a type of firewall capable of both packet inspection and TCP handshake verification. It also has the feature of tracking the status of established connections.

**Threat-Focused NGFW**
Threat-Focused NGFW has all the features of an NGFW-type firewall. In addition, it has advanced threat detection features. Thanks to this feature, it can react quickly to attacks.

**Unified Threat Management (UTM) Firewalls**
Unified Threat Management (UTM) Firewalls are a special type of stateful inspection firewalls with antivirus and intrusion prevention.

### Popular Firewall Products

- Fortinet
- Palo Alto Networks
- SonicWall
- Checkpoint
- Juniper
- pfsense
- Sophos

### Firewall Log Fields

- Date/Time information
- Source IP Address
- Destination IP Address
- Source Port
- Destination Port
- Action Information
- Number of Packets Sent
- Number of Packets Received

## Endpoint Detection and Response (EDR)

Endpoint Detection and Response (EDR) is a security product that is installed on endpoint-qualified devices, constantly monitors the activities in the system, tries to detect security threats such as ransomware & malware, and takes action against malicious activities.

### EDR Core Components

- Endpoint data collection agents
- Automated response
- Analysis and forensics

### EDR Functions

- Monitoring and collecting each process on the device that may identify a security threat
- Analyzing the behavior of threat actors according to the data collected on the device
- Informing the relevant analyst by taking the appropriate security action against the threat actor obtained from the collected data
- Allow forensic analysis on the device to conduct in-depth investigation of suspicious activities

### Popular EDR Products

- SentinelOne
- Crowdstrike
- CarbonBlack
- Palo Alto
- FireEye HX

### EDR Log Sources

EDR product keeps some information as a log by monitoring the system on which it is installed. The processes running on the system are monitored and the names of the files accessed by the programs and their access information are recorded by EDR as logs. It records which programs are run, which files the run programs read, or which file they make changes to.

Endpoint security product provides some information about the processes it lists to the user. Some of this information is size information, hash information, and path information.

## Antivirus Software (AV)

Antivirus Software (AV) is security software that detects malware on devices and blocks and removes malware from the system before it harms the device.

### Types of Antivirus Scanning

**Signature-Based Scanning**
In the signature-based scanning method, the antivirus software scans the system to detect malware with a digital signature, and if there is a matching signature, it marks the file it scans and matches as malicious and clears the file from the system. In this method, digital signatures are kept on the system in the database and must be constantly updated with up-to-date malware signatures.

**Heuristic Scanning**
The heuristic scanning method is a very different malware detection method than the previous signature-based scanning method. Instead of detecting by signature, it monitors the accesses and behaviors of the examined file. In this way, the probability of detecting malicious activities is much higher.

### Antivirus Functions

- To detect malware in the system by constantly scanning the system
- Protecting the system against external threats
- Cleaning detected malware from the system

### Popular Antivirus Products

- McAfee
- Symantec
- Bitdefender
- Eset
- Norton

### Antivirus Log Sources

Antivirus software keeps logs of the findings it obtains in its periodic scans or a special scan of a specific file. These logs contain information about the detected malware. For example, information such as the size of the file, the name of the file, its signature, and the type of malware can be included in the logs.

## Sandbox Solutions

Sandbox is a technology used to run/open and examine executable files or file types with different extensions (pdf, docx, and xlsx, etc.) that are thought or known to be malware in an isolated environment.

### Benefits of Sandboxing

- It does not put hosts and operating systems at risk
- Detects potentially dangerous files
- Allows testing of software updates before they go live
- It allows fighting against 0-day vulnerabilities

### Popular Sandbox Products

- Checkpoint
- McAfee
- Symantec
- Trend Micro
- Proofpoint

### Sandbox Data Sources

When the sample.exe file is run in the sandbox environment, information such as the run time of this file, the files the program accesses after running, its behavior, the date/time information of these operations, and the hash information of this file may be included in the data provided to the user by the sandbox product.

## Data Loss Prevention (DLP)

Data Loss Prevention (DLP) is a technology that prevents sensitive and critical information from leaving the institution.

### Types of DLP

**Network DLP**
Network DLP is responsible for taking security actions related to leaving critical and sensitive information on the network outside the organization. The DLP product may block a connection, request it to be audited, or forward it as a log to the relevant security solution.

**Endpoint DLP**
Unlike Network DLP, Endpoint DLP monitors activities on a particular device rather than packet flow within the network. The Endpoint DLP product is installed on the device and after installation, it manages suspicious activities on the device.

**Cloud DLP**
Cloud DLP is used to prevent sensitive data from leaking over the cloud by working with certain cloud technologies. It is responsible for ensuring that corporate personnel can use cloud applications comfortably without data breaches or loss.

### Popular DLP Products

- Forcepoint
- McAfee
- Trend Micro
- Checkpoint
- Symantec

## Web Application Firewall (WAF)

Web Application Firewall (WAF) is security software or hardware that monitors, filters, and blocks incoming packets to a web application and outgoing packets from a web application.

### Types of WAF

**Network-based WAF**
Network-based WAF is a security product that is hardware-based on the relevant network. It needs staff to write rules on it and to maintain it. Although it is an effective WAF product, it is more expensive than other WAF products.

**Host-based WAF**
Host-based WAF is a cheaper product than network-based WAF. It is a WAF with more customization possibilities. Considering that it is a software product, it consumes the resources of the server it is on.

**Cloud-based WAF**
Cloud-based WAF is a much more convenient and easy-to-apply security solution than other WAF products purchased as an external service. Since the maintenance and updates of the WAF product belong to the service area, there are no additional costs such as cost and maintenance.

### How WAF Works

A WAF manages inbound application traffic according to existing rules on it. These requests, which belong to the HTTP protocol, are either allowed or blocked per the rules. Since it works at the application layer level, it can prevent web-based attacks.

### Popular WAF Products

- AWS
- Cloudflare
- F5
- Citrix
- Fortiweb

## Proxy Server

A proxy Server is hardware or software used for many different purposes and acts as a gateway between client and server.

### Types of Proxy Servers

- **Forward Proxy Server**: This common proxy directs requests from a private network to the internet via a firewall.
- **Transparent Proxy Server**: This proxy directs requests and responses without modifying them.
- **Anonymous Proxy Server**: This proxy allows users to browse the internet anonymously.
- **High Anonymity Proxy Server**: This proxy enhances privacy by obscuring the client's IP address and proxy server type.
- **Reverse Proxy Server**: This proxy validates and processes requests, preventing direct client-server communication.
- **Caching Proxy Server**: This proxy caches responses to improve performance.
- **SSL Proxy Server**: This proxy encrypts traffic between client and server, enhancing security.
- **Rotating Proxy Server**: This proxy assigns a different IP address to each client.

### Proxy Server Benefits

- Private browsing
- Increases user security
- Allows the client's IP address to be hidden
- Allows you to manage network traffic
- Together with the caching mechanism, it saves bandwidth

### Important Note for SOC Analysts

As SOC Analysts, we need to pay attention to the traffic coming from the Proxy while analyzing the servers. Because the source IP address we see does not belong directly to the person concerned, it belongs to the proxy server. What we need to do is to find the real source IP making the request to the proxy server and continue the analysis with these findings.

### Popular Proxy Server Products

- Smartproxy
- Bright Data
- SOAX
- Oxylabs

## Email Security Solutions

Email Security Solutions is one of the security solutions that provides security against threats that may come via e-mail. It can be software or hardware-based products.

### Email Security Functions

- Ensuring the security control of the files in the email
- Ensuring security checks of URLs in the email
- Detection and blocking of spoofed emails
- Blocking known harmful emails
- Blocking email addresses with malicious content detected
- Transmitting information about harmful e-mail content to the relevant product or manager as a warning

Email security solutions are essential for protection against phishing attacks, which are a major threat to both individuals and organizations.

### Popular Email Security Products

- FireEye EX
- IronPort
- TrendMicro Email Security
- Proofpoint
- Symantec
