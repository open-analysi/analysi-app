---
name: cybersecurity-analyst
description: Investigate security alerts, analyze IOCs, triage incidents, and perform threat analysis. Covers SIEM alerts, SOC workflows, malware, phishing, brute force, web attacks, network traffic, and log analysis. Use when building cybersecurity Tasks/Workflows or performing incident response.
version: 0.2.0
---

# Cybersecurity Analyst Skill

## Golden Rules

1. **Evidence before conclusion** — Never classify an alert (TP/FP/inconclusive) without checking at least two independent data sources. A single log line is context, not proof.
2. **Timeline is king** — Build a timeline before analyzing IOCs. The sequence of events (first seen → lateral movement → exfiltration) matters more than any individual indicator.
3. **Attacker-goal reasoning** — Ask "what is the attacker trying to achieve?" before diving into logs. This focuses the investigation on the kill-chain stage (recon → exploitation → persistence → exfiltration) and avoids tunnel vision.
4. **Preserve before you pivot** — Capture volatile evidence (memory, active connections, running processes) before taking containment actions. Containment changes system state.
5. **Correlate on shared fields** — Use `src`, `dest`, `user`, `src_ip`, `dest_ip` to join events across data sources. Misaligned field names are the #1 cause of missed lateral movement.
6. **Severity ≠ priority** — A critical-severity alert on a test box may be lower priority than a medium-severity alert on a domain controller. Always factor in asset criticality.

## Reference Routing Table

| Reference | Read when you need to… |
|-----------|------------------------|
| `siem-alert-investigation.md` | Investigate a SIEM alert end-to-end: understand rule logic, correlate events, classify TP/FP, and document findings |
| `triage-procedures.md` | Perform initial triage — the first questions to ask, checklist-driven assessment, and escalation criteria |
| `malware-analysis.md` | Analyze suspicious files or processes: static/dynamic analysis, sandbox interpretation, and malware family identification |
| `phishing-investigation.md` | Investigate phishing emails: header analysis, URL/attachment analysis, and response procedures |
| `brute-force-attacks.md` | Investigate brute force or credential-stuffing alerts: detection patterns, log correlation, and response |
| `web-attacks.md` | Investigate web application attacks: SQLi, XSS, path traversal, authentication bypass, and WAF log analysis |
| `network-traffic-analysis.md` | Analyze network traffic for C2 beaconing, DNS tunneling, data exfiltration, or lateral movement |
| `log-analysis.md` | Parse and analyze specific log types: netflow, firewall, proxy, DNS, and authentication logs |
| `threat-intelligence.md` | Enrich IOCs with threat intelligence: reputation lookups, CTI frameworks (MITRE ATT&CK, Diamond Model), and feed integration |
| `security-solutions.md` | Understand security tool outputs: IDS/IPS, EDR, SIEM, DLP, and firewall alert formats and field mappings |

