# Project Skaros — NAS to OCSF Alert Schema Migration

## Key Points

- **Clean break**: Replace NAS (our bespoke Normalized Alert Schema) entirely with OCSF v1.8.0 Detection Finding class 2004. No dual-write, no backward compat layer — NAS columns are dropped, not kept alongside.
- **Open-source readiness**: Adopting the industry standard (AWS, Splunk, CrowdStrike, 15+ vendors, Linux Foundation governance) before the first public release. No existing users to migrate.
- **Target class**: OCSF Detection Finding (2004) with profiles: Security Control, OSINT, Host, Cloud, Date/Time, Incident.
- **Cy helper abstraction**: Cy scripts access alert data through helper functions (`get_primary_user()`, `get_src_ip()`, `get_observables()`) that abstract OCSF's nested structure — if the schema ever changes again, only the helpers change, not 35+ tasks.
- **Internal enrichment format preserved**: The dict-keyed enrichment pattern (`alert["enrichments"][cy_name]`) used by 30+ tasks stays unchanged internally.
- **Dedup via `raw_data_hash`**: SHA-256 of `raw_data` content. Replaces the NAS `content_hash` that depended on `primary_*` fields.
- **Existing Python libraries**: `py-ocsf-models` (Pydantic models) and `ocsf-lib` (schema tools) from PyPI.

## Terminology

| Term | Definition |
|------|-----------|
| **NAS** | Normalized Alert Schema — the bespoke schema being replaced. Flat fields (`primary_ioc_value`, `network_info.src_ip`) and IOC/RiskEntity arrays. |
| **OCSF** | Open Cybersecurity Schema Framework — industry standard for security event normalization. v1.8.0 is our target. |
| **Detection Finding (2004)** | The OCSF event class for security alerts/detections. |
| **Profile** | An OCSF overlay that adds optional attributes to event classes (e.g., Security Control adds `disposition_id`, OSINT adds `osint[]`). |
| **Observable** | An OCSF lightweight pointer to a value in the event (type + value). |
| **OSINT object** | The rich IOC model in OCSF (via OSINT profile) — carries confidence, threat_actor, campaign, TLP, kill chain, MITRE ATT&CK. 51 fields. |
| **Evidence Artifacts** | OCSF's typed evidence container — holds `src_endpoint`, `dst_endpoint`, `process`, `file`, `email`, `url`, `http_request`, `http_response`. Replaces NAS's `network_info`, `web_info`, `process_info`, etc. |
| **Cy helper** | A Python function exposed to Cy scripts as a built-in — abstracts OCSF navigation so tasks don't hard-code deep paths like `evidences[0].src_endpoint.ip`. |

## What NAS Has That OCSF Doesn't (Genuine Gaps)

| Gap | Mitigation |
|-----|-----------|
| `primary_*` shortcut fields (11 tasks use as routing keys) | Cy helper functions + first-in-array convention |
| IOC confidence 0-100 granularity (OCSF has 3 buckets) | `osint[].confidence_id` (bucket) + `osint[].reputation.base_score` (original 0-100) |
| Email `spam_score`/`phishing_score` | `enrichments[]` with structured data |
| `human_readable_id` (ALERT-0001) | DB-only column (not part of OCSF schema) |

## What OCSF Gives Us (Free Upgrades)

MITRE ATT&CK mappings, Kill Chain phases, `verdict_id` (FP/TP/Suspicious), `vendor_attributes` (preserve original severity), `is_alert` flag, finding-level confidence/impact/risk scores, `metadata.correlation_uid`, OSINT TLP, detection patterns (STIX/SIGMA/YARA), device posture flags, `anomaly_analyses` (behavioral baselines), `malware_scan_info`, `tickets[]` (Jira/ServiceNow), `ai_operation` profile (LLM tracking), `raw_data_hash` (standard dedup).
