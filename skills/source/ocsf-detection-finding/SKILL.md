---
name: ocsf-detection-finding
version: 0.1.0
description: >-
  Parse, validate, and map OCSF Detection Finding events. Use when normalizing
  security alerts to OCSF, building detection-as-code pipelines, mapping vendor
  alerts to MITRE ATT&CK, extracting observables, or working with finding_info
  structures and severity/status enums.
---

# OCSF Detection Finding (Class 2004 v1.8.0)

Detection Finding events represent alerts from security products — correlation engines, EDR, SIEM rules, ML models, or cloud-native detectors. Class UID is always `2004`, category is Findings (`category_uid: 2`). The `type_uid` is derived as `class_uid × 100 + activity_id` (e.g., 200401 for Create).

Apply the `security_control` profile when the producer is a security control. Use the `incident` profile when findings feed into incident workflows.

## Reference Loading Guide

| Reference | Read when | Consult for |
|-----------|-----------|-------------|
| `references/attributes.md` | Building or validating a Detection Finding event | All top-level attributes, requirement levels, type_uid calculation, severity/status/confidence/impact/risk enums, activity enum |
| `references/finding-info.md` | Working with detection rule metadata or finding details | finding_info fields, Analytic object (type_id, state_id enums), related_analytics, related_events |
| `references/attack-mappings.md` | Mapping to MITRE ATT&CK or Cyber Kill Chain | Attack object structure, tactic/technique/sub_technique constraints, common tactic IDs, kill_chain phase_id values |
| `references/metadata-profiles.md` | Setting product info, log source, or applying profiles | Metadata object, Product object, profile list, Security Control / Cloud profile attributes |
| `references/observables-evidence.md` | Extracting IOCs or examining triggering evidence | Observable type_id enum (0–48), Reputation object, Evidence Artifacts fields, verdict_id enum |
| `references/examples.md` | Constructing or reviewing Detection Finding JSON | Minimal event, full EDR alert, cloud detection, Update/Close events, vendor mapping patterns, validation checklist |

## Decision Path

- **Creating a new Detection Finding** → Read `attributes.md` for required fields, then `examples.md` for templates
- **Mapping vendor alerts to OCSF** → Start with `examples.md` for target shape, consult `attributes.md` for enums, `finding-info.md` for analytic type mapping, `observables-evidence.md` for IOC extraction
- **Validating an existing event** → Check required fields against `attributes.md`, verify `type_uid = class_uid × 100 + activity_id`, validate `finding_info` via `finding-info.md`
- **Enriching with MITRE ATT&CK** → Read `attack-mappings.md` for the nested attack object structure and common tactic IDs
- **Investigating a detection** → Read `observables-evidence.md` for IOC type codes and evidence artifact interpretation

## Key Constraints

- `type_uid` must equal `class_uid × 100 + activity_id` (e.g., 200401 for Create)
- `finding_info.uid` is the only required field inside `finding_info`; at least one of `analytic.name` or `analytic.uid` must be present when analytic is included
- Evidence Artifacts require at least one substantive attribute (actor, file, process, query, device, etc.)
- MITRE ATT&CK object requires at least one of `technique`, `tactic`, or `sub_technique`
- `tactics` (plural array) is deprecated since v1.1.0 — use singular `tactic` object
- Applicable profiles: Cloud, Container, Data Classification, Date/Time, Host, Incident, Linux Users, macOS Users, OSINT, Security Control
