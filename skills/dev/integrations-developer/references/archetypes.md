# Naxos Integration Archetypes

## Overview
Every Naxos integration MUST declare at least one archetype. Archetypes define standardized abstract actions that enable Cy scripts to work with any integration of that type without knowing the specific implementation.

## Important Note on Return Types

The method signatures below use typed returns (e.g., `-> ThreatIndicator`, `-> Status`) to describe the *expected shape* of the response. In practice, all `IntegrationAction.execute()` methods return `dict[str, Any]`. The typed signatures are a design reference showing what fields the dict should contain.

## Core Archetypes & Abstract Actions

### 1. ThreatIntel (Threat Intelligence)
**Examples**: VirusTotal, AbuseIPDB, AlienVault OTX, ThreatConnect, RecordedFuture

**Abstract Actions**:
```python
class ThreatIntelArchetype:
    async def lookup_ip(self, ip: str) -> ThreatIndicator
    async def lookup_domain(self, domain: str) -> ThreatIndicator
    async def lookup_file_hash(self, hash: str) -> ThreatIndicator
    async def lookup_url(self, url: str) -> ThreatIndicator
    async def lookup_email(self, email: str) -> ThreatIndicator
    async def get_threat_context(self, ioc: str) -> EnrichmentData
    async def submit_ioc(self, ioc: str, threat_level: int) -> Status
```

### 2. SIEM (Security Information and Event Management)
**Examples**: Splunk, QRadar, ArcSight, Elastic SIEM, Sumo Logic

**Abstract Actions**:
```python
class SIEMArchetype:
    async def query_events(self, query: str, time_range: TimeRange) -> List[Event]
    async def create_alert(self, alert: Alert) -> str
    async def update_alert_status(self, alert_id: str, status: str) -> Status
    async def get_alert_details(self, alert_id: str) -> Alert
    async def run_saved_search(self, search_name: str) -> SearchResults
    async def get_alerts(self, time_range: TimeRange) -> List[Alert]
    async def add_threat_intel(self, indicators: List[IOC]) -> Status
```

### 3. EDR (Endpoint Detection and Response)
**Examples**: CrowdStrike Falcon, Carbon Black, Microsoft Defender, SentinelOne

**Abstract Actions**:
```python
class EDRArchetype:
    async def isolate_host(self, host_id: str) -> Status
    async def release_host(self, host_id: str) -> Status
    async def scan_host(self, host_id: str, scan_type: str) -> ScanResults
    async def get_host_details(self, host_id: str) -> HostInfo
    async def kill_process(self, host_id: str, process_id: str) -> Status
    async def quarantine_file(self, host_id: str, file_path: str) -> Status
    async def collect_forensics(self, host_id: str) -> ForensicsPackage
    async def run_script(self, host_id: str, script: str) -> ScriptOutput
```

### 4. SOAR (Security Orchestration, Automation & Response)
**Examples**: Phantom, Demisto/XSOAR, Swimlane, Tines, InsightConnect

**Abstract Actions**:
```python
class SOARArchetype:
    async def create_incident(self, incident: Incident) -> str
    async def update_incident(self, incident_id: str, updates: dict) -> Status
    async def run_playbook(self, playbook_name: str, params: dict) -> PlaybookResult
    async def get_incident_timeline(self, incident_id: str) -> List[TimelineEntry]
    async def add_artifact(self, incident_id: str, artifact: Artifact) -> Status
    async def close_incident(self, incident_id: str, resolution: str) -> Status
```

### 5. TicketingSystem
**Examples**: ServiceNow, Jira, PagerDuty, Zendesk, Remedy

**Abstract Actions**:
```python
class TicketingArchetype:
    async def create_ticket(self, ticket: Ticket) -> str
    async def update_ticket(self, ticket_id: str, updates: dict) -> Status
    async def assign_ticket(self, ticket_id: str, assignee: str) -> Status
    async def add_comment(self, ticket_id: str, comment: str) -> Status
    async def escalate_ticket(self, ticket_id: str, level: int) -> Status
    async def close_ticket(self, ticket_id: str, resolution: str) -> Status
    async def get_ticket_status(self, ticket_id: str) -> TicketStatus
```

### 6. Communication
**Examples**: Slack, Microsoft Teams, Email, Twilio, PagerDuty, Webex

**Abstract Actions**:
```python
class CommunicationArchetype:
    async def send_message(self, recipient: str, message: str) -> Status
    async def send_alert(self, recipients: List[str], alert: Alert) -> Status
    async def create_channel(self, channel_name: str) -> str
    async def post_to_channel(self, channel_id: str, message: str) -> Status
    async def send_file(self, recipient: str, file_path: str) -> Status
    async def start_conference(self, participants: List[str]) -> ConferenceInfo
```

### 7. CloudProvider
**Examples**: AWS, Azure, GCP, Oracle Cloud, Alibaba Cloud

**Abstract Actions**:
```python
class CloudProviderArchetype:
    async def list_instances(self, filters: dict = None) -> List[Instance]
    async def stop_instance(self, instance_id: str) -> Status
    async def start_instance(self, instance_id: str) -> Status
    async def create_snapshot(self, instance_id: str) -> str
    async def get_security_findings(self) -> List[Finding]
    async def update_security_group(self, sg_id: str, rules: List[Rule]) -> Status
    async def get_cost_report(self, time_range: TimeRange) -> CostReport
    async def enable_logging(self, resource_id: str) -> Status
```

### 8. NetworkSecurity
**Examples**: Palo Alto, Fortinet, Check Point, Cisco ASA, pfSense

**Abstract Actions**:
```python
class NetworkSecurityArchetype:
    async def block_ip(self, ip: str, duration: int = None) -> Status
    async def unblock_ip(self, ip: str) -> Status
    async def block_url(self, url: str) -> Status
    async def create_rule(self, rule: FirewallRule) -> str
    async def get_traffic_logs(self, time_range: TimeRange) -> List[TrafficLog]
    async def get_threat_logs(self, time_range: TimeRange) -> List[ThreatLog]
    async def update_policy(self, policy_id: str, updates: dict) -> Status
```

### 9. IdentityProvider
**Examples**: Okta, Active Directory, Azure AD, Duo, Ping Identity

**Abstract Actions**:
```python
class IdentityProviderArchetype:
    async def disable_user(self, user_id: str) -> Status
    async def enable_user(self, user_id: str) -> Status
    async def reset_password(self, user_id: str) -> TemporaryPassword
    async def get_user_details(self, user_id: str) -> UserInfo
    async def add_to_group(self, user_id: str, group_id: str) -> Status
    async def revoke_sessions(self, user_id: str) -> Status
    async def enable_mfa(self, user_id: str) -> Status
    async def get_authentication_logs(self, user_id: str) -> List[AuthLog]
```

### 10. VulnerabilityManagement
**Examples**: Qualys, Tenable, Rapid7, Nessus, OpenVAS

**Abstract Actions**:
```python
class VulnerabilityManagementArchetype:
    async def scan_assets(self, asset_ids: List[str]) -> str
    async def get_vulnerabilities(self, severity: str = None) -> List[Vulnerability]
    async def get_asset_vulnerabilities(self, asset_id: str) -> List[Vulnerability]
    async def create_exception(self, vuln_id: str, reason: str) -> Status
    async def get_compliance_status(self) -> ComplianceReport
    async def schedule_scan(self, targets: List[str], schedule: str) -> str
```

### 11. Sandbox (Malware Analysis)
**Examples**: Cuckoo, Joe Sandbox, Any.run, VMRay, Hybrid Analysis

**Abstract Actions**:
```python
class SandboxArchetype:
    async def submit_file(self, file_path: str) -> str
    async def submit_url(self, url: str) -> str
    async def get_analysis_status(self, analysis_id: str) -> AnalysisStatus
    async def get_analysis_report(self, analysis_id: str) -> SandboxReport
    async def get_iocs(self, analysis_id: str) -> List[IOC]
    async def get_network_traffic(self, analysis_id: str) -> NetworkCapture
    async def download_sample(self, hash: str) -> bytes
```

### 12. EmailSecurity
**Examples**: Proofpoint, Mimecast, IronPort, Exchange Online Protection

**Abstract Actions**:
```python
class EmailSecurityArchetype:
    async def quarantine_email(self, message_id: str) -> Status
    async def release_email(self, message_id: str) -> Status
    async def block_sender(self, email: str) -> Status
    async def unblock_sender(self, email: str) -> Status
    async def get_email_trace(self, message_id: str) -> EmailTrace
    async def submit_phishing(self, email_content: str) -> AnalysisResult
    async def update_spam_policy(self, policy: SpamPolicy) -> Status
```

### 13. CloudStorage
**Examples**: Box, Dropbox, Google Drive, OneDrive, S3

**Abstract Actions**:
```python
class CloudStorageArchetype:
    async def upload_file(self, file_path: str, destination: str) -> str
    async def download_file(self, file_id: str) -> bytes
    async def delete_file(self, file_id: str) -> Status
    async def share_file(self, file_id: str, recipients: List[str]) -> ShareLink
    async def revoke_access(self, file_id: str, user_id: str) -> Status
    async def scan_for_malware(self, file_id: str) -> ScanResult
    async def get_file_metadata(self, file_id: str) -> FileMetadata
```

### 14. DatabaseEnrichment
**Examples**: Shodan, Censys, BinaryEdge, ZoomEye, Criminal IP

**Abstract Actions**:
```python
class DatabaseEnrichmentArchetype:
    async def search_hosts(self, query: str) -> List[Host]
    async def get_host_details(self, ip: str) -> HostEnrichment
    async def search_certificates(self, query: str) -> List[Certificate]
    async def get_open_ports(self, ip: str) -> List[Port]
    async def get_technologies(self, domain: str) -> List[Technology]
    async def get_vulnerabilities(self, ip: str) -> List[CVE]
```

### 15. ForensicsTools
**Examples**: TheHive, MISP, Volatility, Autopsy, X-Ways

**Abstract Actions**:
```python
class ForensicsArchetype:
    async def create_case(self, case: Case) -> str
    async def add_evidence(self, case_id: str, evidence: Evidence) -> Status
    async def analyze_memory_dump(self, dump_path: str) -> MemoryAnalysis
    async def extract_artifacts(self, image_path: str) -> List[Artifact]
    async def timeline_analysis(self, case_id: str) -> Timeline
    async def generate_report(self, case_id: str) -> ForensicsReport
```

### 16. Geolocation
**Examples**: MaxMind, IPinfo, IP2Location, ipapi, GeoIP2

**Abstract Actions**:
```python
class GeolocationArchetype:
    async def lookup_ip_location(self, ip: str) -> Location
    async def get_asn_info(self, ip: str) -> ASNInfo
    async def get_timezone(self, ip: str) -> str
    async def is_vpn(self, ip: str) -> bool
    async def is_tor_exit(self, ip: str) -> bool
    async def get_isp_details(self, ip: str) -> ISPInfo
```

### 17. AI (Artificial Intelligence / LLM Providers)
**Examples**: OpenAI (priority 80), Anthropic (priority 90), Google Gemini (priority 75)

**Abstract Actions**:
```python
class AIArchetype:
    async def llm_run(self, prompt: str, context: str = None, capability: str = "default") -> LLMResponse
    async def llm_chat(self, messages: List[Message], capability: str = "default") -> ChatResponse
    async def llm_embed(self, text: str) -> EmbeddingVector
```

`llm_run` is convenience sugar over `llm_chat` — wraps the prompt in a messages array and extracts the response string. Not all providers support `llm_embed` (e.g., Anthropic sets `"embedding": null` in presets).

**Capability-Based Model Presets**: Each AI provider defines named presets in `settings_schema.model_presets`:

| Capability | Purpose | Example (OpenAI) | Example (Anthropic) |
|------------|---------|-------------------|---------------------|
| `default` | Balanced cost/quality | `gpt-4o` | `claude-sonnet-4-20250514` |
| `thinking` | Deep reasoning | `o3` | `claude-sonnet-4` + extended thinking |
| `fast` | Low latency, cheap | `gpt-4o-mini` | `claude-haiku-3-20250307` |
| `long_context` | Large context window | `gpt-4o` | `claude-opus-4-20250514` |
| `embedding` | Text embeddings | `text-embedding-3-small` | `null` (not supported) |

Presets are dicts — `"thinking"` for Anthropic is the same model with `{"extended_thinking": true}`. An explicit `null` means "not supported" and raises `ValueError`. Unknown capabilities fall back to `"default"`.

**Priority Guidance**: 80 (standard), 90 for Anthropic (dual AI + AgenticFramework archetype)

**Cy Integration**:
```python
# Call any AI provider via archetype routing
result = ai::llm_run("Analyze this alert for threats")

# With capability selection
result = ai::llm_run("Analyze this alert", capability="thinking")

# Or call specific provider
result = app:openai::llm_run("Analyze this alert")
```

### 18. DNS (Domain Name System)
**Examples**: Global DNS (free public resolvers), Cloudflare DNS, Google Public DNS, Quad9

**Abstract Actions**:
```python
class DNSArchetype:
    async def resolve_domain(self, domain: str, record_type: str = "A") -> List[str]
    async def reverse_lookup(self, ip: str) -> str
    async def get_mx_records(self, domain: str) -> List[MXRecord]
    async def get_txt_records(self, domain: str) -> List[str]
    async def get_ns_records(self, domain: str) -> List[str]
    async def get_soa_record(self, domain: str) -> SOARecord
```

**Priority Guidance**: 60 (standard for enrichment/lookup services)

**Use Cases**:
- Phishing investigation (resolve suspicious domains, check MX/SPF records)
- C2 infrastructure analysis (reverse DNS on known bad IPs)
- Email authentication (SPF, DKIM, DMARC via TXT records)
- Domain verification (check nameservers, SOA records)

**DNS vs Other Archetypes**:
- **DNS**: Basic DNS protocol queries (free, public resolvers like 8.8.8.8)
- **ThreatIntel**: Domain reputation, threat scoring, historical data (e.g., DomainTools)
- **DatabaseEnrichment**: Passive DNS databases, historical records (e.g., SecurityTrails)

**Important**: DNS archetype is for **basic DNS resolution only**. Domain intelligence features like WHOIS, historical records, reputation scoring belong in ThreatIntel or DatabaseEnrichment archetypes.

**Future Cy Integration**: These actions will enable archetype-based routing in Cy scripts:
```python
# Resolve domain to IPs
ips = dns::resolve_domain(domain="example.com")

# Reverse DNS lookup
hostname = dns::reverse_lookup(ip="8.8.8.8")

# Check email authentication
mx_records = dns::get_mx_records(domain="gmail.com")
spf_record = dns::get_txt_records(domain="google.com")
```

### 19. Notification
**Examples**: PagerDuty (alerting), Opsgenie, custom webhook dispatchers

**Abstract Actions**:
```python
class NotificationArchetype:
    async def send_notification(self, message: str, severity: str) -> Status
    async def acknowledge_notification(self, notification_id: str) -> Status
    async def resolve_notification(self, notification_id: str) -> Status
```

### 20. Lakehouse (Data Lake / Warehouse)
**Examples**: BigQuery, Databricks, Snowflake, AWS Athena

**Abstract Actions**:
```python
class LakehouseArchetype:
    async def run_query(self, query: str) -> QueryResults
    async def list_tables(self, dataset: str = None) -> list[str]
    async def get_table_schema(self, table: str) -> TableSchema
```

### 21. AgenticFramework (AI Agent Orchestration)
**Examples**: Anthropic (Claude Code agent), LangGraph, CrewAI

**Abstract Actions**:
```python
class AgenticFrameworkArchetype:
    async def run_agent(self, prompt: str, tools: list[str] = None) -> AgentResult
```

**Note**: The Anthropic integration implements both `AI` and `AgenticFramework` archetypes.

### 22. AlertSource (Alert Ingestion)
**Examples**: Splunk (pull_alerts + OCSF normalization)

**Abstract Actions**:
```python
class AlertSourceArchetype:
    async def pull_alerts(self, lookback_minutes: int = None) -> list[Alert]
    async def alerts_to_ocsf(self, alerts: list[dict]) -> list[DetectionFinding]
```

**Required methods**: Both `pull_alerts` and `alerts_to_ocsf` must be mapped — the framework enforces this.

**Note**: AlertSource is for integrations that both ingest alerts AND normalize them to OCSF format. SIEM integrations that only query events use the `SIEM` archetype instead.

## Archetype Declaration in Manifest

Each integration's `manifest.json` must declare its archetypes:

```json
{
  "id": "virustotal",
  "app": "virustotal",
  "archetypes": ["ThreatIntel", "Sandbox"],

  "archetype_mappings": {
    "ThreatIntel": {
      "lookup_ip": "lookup_ip",
      "lookup_domain": "lookup_domain",
      "lookup_file_hash": "lookup_file",
      "lookup_url": "lookup_url"
    },
    "Sandbox": {
      "submit_file": "detonate_file",
      "get_analysis_report": "get_file_report"
    }
  }
}
```

## Benefits of Archetypes

1. **Standardization**: Cy scripts can work with any integration of the same archetype
2. **Discoverability**: Easy to find all ThreatIntel or SIEM integrations
3. **Validation**: Ensure integrations implement required abstract actions
4. **Substitutability**: Switch providers without changing scripts
5. **Documentation**: Clear expectations for each integration type

## Implementation Pattern

Archetypes are declared in `manifest.json` and resolved at runtime via the registry:

```json
// In manifest.json — declare archetypes (PascalCase) and map methods to action IDs
{
  "archetypes": ["ThreatIntel", "Sandbox"],
  "archetype_mappings": {
    "ThreatIntel": {
      "lookup_ip": "ip_reputation",
      "lookup_domain": "domain_reputation"
    },
    "Sandbox": {
      "submit_file": "detonate_file",
      "get_analysis_report": "get_file_report"
    }
  }
}
```

```python
# Action class — naming convention: action_id → PascalCase + "Action"
# ip_reputation → IpReputationAction
class IpReputationAction(IntegrationAction):
    async def execute(self, **kwargs) -> dict[str, Any]:
        ip = kwargs.get("ip")
        response = await self.http_request(url=f"{base_url}/v1/ip/{ip}")
        data = response.json()
        return self.success_result(data={
            "score": data["malicious_score"],
            "reputation": data["reputation"],
        })
```

Archetype-based routing is handled by `resolve_archetype_action()` in the registry — it finds the highest-priority integration that serves a given archetype and action.
