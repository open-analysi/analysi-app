# MITRE ATT&CK & Kill Chain Mappings Reference

Source: [OCSF v1.8.0 Attack Object](https://schema.ocsf.io/1.8.0/objects/attack) | [Kill Chain Phase](https://schema.ocsf.io/1.8.0/objects/kill_chain_phase)

## Table of Contents
- [Attack Object](#attack-object)
- [Tactic Object](#tactic-object)
- [Technique Object](#technique-object)
- [Sub-Technique Object](#sub-technique-object)
- [Kill Chain Phase Object](#kill-chain-phase-object)
- [Mapping Patterns](#mapping-patterns)

---

## Attack Object

Located at `finding_info.attacks[]`. Each entry maps the detection to a MITRE ATT&CK tactic/technique pair.

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `tactic` | Tactic Object | Recommended | ATT&CK tactic — see below |
| `technique` | Technique Object | Recommended | ATT&CK technique — see below |
| `sub_technique` | Sub-Technique Object | Recommended | ATT&CK sub-technique — see below |
| `version` | String | Recommended | ATT&CK Matrix version (e.g., `"v14"`, `"v15"`) |
| `mitigation` | Mitigation Object | Optional | Recommended mitigation from ATT&CK |
| `tactics` | Tactic[] | *Deprecated v1.1.0* | Use singular `tactic` instead |

**Constraint:** At least one of `tactic`, `technique`, or `sub_technique` must be present.

---

## Tactic Object

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `uid` | String | Recommended* | Tactic ID (e.g., `"TA0001"`) |
| `name` | String | Recommended* | Tactic name (e.g., `"Initial Access"`) |
| `src_url` | URL String | Optional | Permalink (e.g., `"https://attack.mitre.org/versions/v14/tactics/TA0001/"`) |

*Constraint: at least one of `name` or `uid` must be present.*

### Common Tactic IDs

| UID | Name |
|-----|------|
| TA0043 | Reconnaissance |
| TA0042 | Resource Development |
| TA0001 | Initial Access |
| TA0002 | Execution |
| TA0003 | Persistence |
| TA0004 | Privilege Escalation |
| TA0005 | Defense Evasion |
| TA0006 | Credential Access |
| TA0007 | Discovery |
| TA0008 | Lateral Movement |
| TA0009 | Collection |
| TA0011 | Command and Control |
| TA0010 | Exfiltration |
| TA0040 | Impact |

---

## Technique Object

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `uid` | String | Recommended* | Technique ID (e.g., `"T1566"` for Phishing) |
| `name` | String | Recommended* | Technique name |
| `src_url` | URL String | Optional | Permalink |

*Constraint: at least one of `name` or `uid` must be present.*

---

## Sub-Technique Object

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `uid` | String | Recommended* | Sub-technique ID (e.g., `"T1566.001"`) |
| `name` | String | Recommended* | Sub-technique name |
| `src_url` | URL String | Optional | Permalink |

*Constraint: at least one of `name` or `uid` must be present.*

---

## Kill Chain Phase Object

Located at `finding_info.kill_chain[]`. Maps the detection to Lockheed Martin Cyber Kill Chain phases.

| Field | Type | Req | Description |
|-------|------|-----|-------------|
| `phase_id` | Integer | **Required** | Phase identifier — see enum below |
| `phase` | String | Recommended | Phase caption |

### phase_id Enum

| ID | Phase | Description |
|----|-------|-------------|
| 0 | Unknown | Phase not determined |
| 1 | Reconnaissance | Information gathering, vulnerability scanning |
| 2 | Weaponization | Exploit/payload development |
| 3 | Delivery | Phishing, watering hole, infected media |
| 4 | Exploitation | Vulnerability exploitation, code execution |
| 5 | Installation | Malware/implant deployment on target |
| 6 | Command & Control | C2 channel establishment |
| 7 | Actions on Objectives | Data theft, destruction, mission completion |
| 99 | Other | Non-standard phase; check `phase` string |

---

## Mapping Patterns

### Single technique with tactic

```json
"attacks": [
  {
    "tactic": {"uid": "TA0002", "name": "Execution"},
    "technique": {"uid": "T1059", "name": "Command and Scripting Interpreter"},
    "sub_technique": {"uid": "T1059.001", "name": "PowerShell"},
    "version": "v14"
  }
]
```

### Multiple tactics (detection spans phases)

A technique may appear under multiple tactics. Create separate attack entries for each tactic association.

```json
"attacks": [
  {
    "tactic": {"uid": "TA0003", "name": "Persistence"},
    "technique": {"uid": "T1547", "name": "Boot or Logon Autostart Execution"},
    "version": "v14"
  },
  {
    "tactic": {"uid": "TA0004", "name": "Privilege Escalation"},
    "technique": {"uid": "T1547", "name": "Boot or Logon Autostart Execution"},
    "version": "v14"
  }
]
```

### Kill chain combined with ATT&CK

When both `attacks` and `kill_chain` are present, they provide complementary views. ATT&CK gives specificity (exact technique), Kill Chain gives phase context. They do not need to align 1:1.

```json
"finding_info": {
  "uid": "DET-001",
  "attacks": [
    {"tactic": {"uid": "TA0002"}, "technique": {"uid": "T1059.001"}, "version": "v14"}
  ],
  "kill_chain": [
    {"phase_id": 4, "phase": "Exploitation"}
  ]
}
```
