# Integrations

Analysi ships with a pluggable integration framework (**Naxos**) and **101 built-in integrations**. Each integration declares one or more **archetypes** (what kind of tool it is) and exposes one or more **actions** (capabilities callable from Cy scripts, scheduled jobs, or via the API for ad-hoc execution).

See the [Terminology](terminology.md#integrations) page for the formal definitions of *Integration*, *Archetype*, and *Action*.

## By archetype

The 27 archetypes registered in the codebase are listed below. Counts include the integrations that declare each archetype — many integrations declare more than one (e.g. CrowdStrike is both EDR and Sandbox), so per-archetype counts sum to more than 101.

| Archetype | # | Examples |
|-----------|---|----------|
| ThreatIntel | 19 | VirusTotal, AbuseIPDB, Recorded Future, MISP, Shodan, GreyNoise, DomainTools |
| EDR | 13 | CrowdStrike, SentinelOne, Defender for Endpoint, Carbon Black, Cortex XDR, Echo EDR |
| NetworkSecurity | 11 | Palo Alto, FortiGate, Check Point, Zscaler, Cloudflare, Cisco Umbrella, Netskope |
| SIEM | 10 | Splunk, Microsoft Sentinel, Elasticsearch, QRadar, Chronicle, Sumo Logic, Exabeam |
| EmailSecurity | 6 | Proofpoint, Mimecast, Abnormal, Google Gmail, Exchange On-Prem, Cofense Triage |
| DatabaseEnrichment | 6 | Censys, SecurityTrails, Have I Been Pwned, NIST NVD, Axonius, PassiveTotal |
| IdentityProvider | 5 | Okta, Microsoft Entra ID, AD LDAP, Duo, CyberArk |
| TicketingSystem | 5 | JIRA, ServiceNow, TheHive, Freshservice, BMC Remedy |
| Sandbox | 5 | ANY.RUN, Joe Sandbox, WildFire, urlscan.io, CrowdStrike |
| CloudProvider | 4 | AWS Security, Google Cloud SCC, Defender for Cloud, Wiz |
| VulnerabilityManagement | 4 | Tenable, Qualys, Rapid7 InsightVM, Nessus |
| AI | 3 | Anthropic (Claude), OpenAI, Google Gemini |
| Communication | 3 | Microsoft Teams, Cisco Webex, Google Chat |
| Lakehouse | 2 | Databricks, Google BigQuery |
| Notification | 2 | Slack, PagerDuty |
| DNS · Geolocation · MacOuiRegistry · QRDecoder · TorExitList · UrlShorteningTools · Whois | 1 each | Global DNS, MaxMind, MAC Vendors, QR Code, Tor, unshorten.me, WHOIS RDAP |

The remaining archetypes are registered in the framework but currently have no shipped integrations: **SOAR**, **CloudStorage**, **ForensicsTools**, **AgenticFramework**, **AlertSource**.

## Adding an integration

Drop a directory under [`src/analysi/integrations/framework/integrations/`](https://github.com/open-analysi/analysi-app/tree/main/src/analysi/integrations/framework/integrations) with:

- `manifest.json` — declares archetypes, actions, input/output schemas, auth requirements
- An `IntegrationAction` subclass per action — implements `async execute()`

Validate with:

```bash
poetry run validate-integration src/analysi/integrations/framework/integrations/<your-integration>
```
