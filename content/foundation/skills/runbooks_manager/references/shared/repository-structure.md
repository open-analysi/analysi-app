# ../runbooks-y Repository Structure

## Overview

The `../runbooks-y` repository contains all security investigation runbooks organized hierarchically for maximum reusability and maintainability. The structure enables both specific detection runbooks and reusable investigation patterns.

## Directory Layout

```
../runbooks-y/
├── common/                          # Reusable sub-runbooks
│   ├── universal/                   # Always applicable patterns
│   ├── by_source/                   # Source-category specific
│   ├── by_type/                     # Alert-type specific
│   ├── evidence/                    # Evidence collection patterns
│   ├── enrichment/                  # External enrichment patterns
│   └── analysis/                    # Analysis patterns
├── detections/                      # Detection-specific runbooks
│   ├── web/                         # Web source_category
│   ├── endpoint/                    # EDR source_category
│   ├── identity/                    # Identity source_category
│   ├── email/                       # Email source_category
│   └── network/                     # Network source_category
├── templates/                       # Templates for new runbooks
└── README.md                        # Repository documentation
```

## Directory Details

### /common/universal/

**Purpose:** Patterns that apply to ALL runbooks regardless of type or source.

**Contents:**
- `alert-understanding.md` - Standard alert comprehension and hypothesis formation
- `final-analysis-trio.md` - The mandatory final analysis pattern (detailed → disposition + summary)

**Usage:** Almost every runbook includes these via WikiLinks (`![[path.md]]`).

### /common/by_source/

**Purpose:** Patterns specific to a source_category from the OCSF schema.

**Structure:** One file per source_category.

**Examples:**
```
by_source/
├── web_common.md           # Common for Web/WAF alerts
├── edr_common.md           # Common for EDR alerts
├── identity_common.md      # Common for Identity/IAM alerts
├── email_common.md         # Common for Email Security alerts
├── firewall_common.md      # Common for Firewall alerts
└── cloud_common.md         # Common for Cloud Security alerts
```

**Content Example (web_common.md):**
- HTTP header analysis patterns
- URL decoding steps
- Web-specific SIEM queries
- Response code interpretation

### /common/by_type/

**Purpose:** Patterns specific to an alert_type regardless of source.

**Structure:** One file per major alert type.

**Examples:**
```
by_type/
├── sql_injection_base.md    # All SQL injection investigations
├── xss_base.md              # All XSS investigations
├── brute_force_base.md      # All brute force investigations
├── phishing_base.md         # All phishing investigations
├── malware_base.md          # All malware investigations
├── data_exfil_base.md       # All data exfiltration investigations
└── privilege_escalation_base.md
```

**Content Example (sql_injection_base.md):**
- SQL payload analysis
- Database impact assessment
- Common SQL injection patterns
- Data extraction indicators

### /common/evidence/

**Purpose:** Reusable evidence collection patterns.

**Contents:**
```
evidence/
├── siem_evidence_collection.md     # Parameterized SIEM queries
├── splunk_patterns.md             # Splunk-specific query patterns
├── endpoint_telemetry.md          # EDR evidence collection
├── network_activity.md            # Network traffic analysis
└── user_activity.md               # User behavior evidence
```

**Features:**
- Parameterized queries (${variable} substitution)
- Time window specifications
- Correlation patterns

### /common/enrichment/

**Purpose:** External enrichment patterns.

**Contents:**
```
enrichment/
├── threat_intel_enrichment.md     # Multi-source threat intelligence
├── ip_reputation.md               # IP-specific enrichment
├── domain_reputation.md           # Domain analysis
├── file_hash_analysis.md          # Malware hash lookups
├── user_context.md                # AD/LDAP user enrichment
└── asset_inventory.md             # CMDB/asset lookups
```

### /common/analysis/

**Purpose:** Analysis and decision-making patterns.

**Contents:**
```
analysis/
├── hypothesis_validation.md       # Standard hypothesis testing
├── attack_success_determination.md # Did the attack succeed?
├── impact_assessment.md           # Business impact analysis
├── false_positive_detection.md    # FP pattern recognition
└── escalation_decision.md         # When to escalate
```

## /detections/ Directory Structure

### Organization Hierarchy

```
detections/
└── {source_category}/              # Level 1: By source
    └── {alert_type}/                # Level 2: By type
        └── {detection_rule}.md      # Level 3: Specific rule
```

### Examples

```
detections/
├── web/
│   ├── sql_injection/
│   │   ├── apache_modsec_union_select.md
│   │   ├── nginx_waf_blind_sqli.md
│   │   └── cloudflare_sql_blocked.md
│   ├── xss/
│   │   ├── reflected_xss_in_search.md
│   │   └── stored_xss_in_comments.md
│   └── command_injection/
│       └── os_command_execution.md
├── endpoint/
│   ├── powershell/
│   │   ├── encoded_command_execution.md
│   │   ├── suspicious_download_cradle.md
│   │   └── amsi_bypass_attempt.md
│   ├── process_injection/
│   │   └── process_hollowing_detected.md
│   └── ransomware/
│       └── mass_file_encryption.md
├── identity/
│   ├── brute_force/
│   │   ├── ad_password_spray.md
│   │   └── okta_rate_limit_exceeded.md
│   └── privilege_escalation/
│       └── admin_group_addition.md
└── email/
    ├── phishing/
    │   ├── credential_harvesting_link.md
    │   └── executive_impersonation.md
    └── malware/
        └── malicious_attachment.md
```

## Naming Conventions

### Files

**Detection Runbooks:**
- Format: `{detection_rule_snake_case}.md`
- Example: `suspicious_powershell_encoded_command.md`
- Match detection rule name as closely as possible

**Sub-Runbooks:**
- Format: `{pattern_description}.md`
- Example: `threat_intel_enrichment.md`
- Use descriptive names indicating the pattern

### Directories

**Source Categories:**
- Use lowercase OCSF source_category
- Examples: `web`, `edr`, `identity`, `email`

**Alert Types:**
- Use lowercase with underscores
- Examples: `sql_injection`, `brute_force`, `phishing`

## File Discovery Patterns

### Finding a Specific Runbook

```python
# Priority order for runbook discovery:
1. Exact match: detections/{source}/{type}/{detection_rule}.md
2. Type pattern: common/by_type/{alert_type}_base.md
3. Source pattern: common/by_source/{source}_common.md
4. Universal: common/universal/
```

### Include Path Resolution

**Absolute paths from repository root:**
```markdown
![[common/universal/alert-understanding.md]]
![[common/by_type/sql_injection_base.md]]
```

**Never use relative paths:**
```markdown
![[../common/universal/alert-understanding.md]]  # WRONG
![[./sub_runbook.md]]                            # WRONG
```

## Templates Directory

### Purpose
Provide starting points for new runbooks.

### Contents
```
templates/
├── detection_template.md          # Blank detection runbook
├── sub_runbook_template.md        # Blank sub-runbook
└── examples/
    ├── simple_detection.md        # Minimal example
    └── complex_detection.md       # Full-featured example
```

## Best Practices

### Organization
1. **Start specific:** Create detection-specific runbook first
2. **Extract patterns:** After 3+ similar runbooks, extract to common/
3. **Maintain hierarchy:** Always follow source → type → detection structure
4. **Use metadata:** Properly categorize with alert_type and source_category

### Reusability
1. **DRY Principle:** Don't duplicate, use WikiLinks (`![[path.md]]`)
2. **Parameterize:** Use ${variables} for flexible sub-runbooks
3. **Document patterns:** Add comments in sub-runbooks explaining usage

### Maintenance
1. **Version control:** Track changes to runbooks
2. **Test changes:** Validate WikiLink paths when reorganizing
3. **Update references:** When moving files, update all WikiLink includes

## Repository Evolution

### Phase 1: Initial Population
- Create detection-specific runbooks
- Minimal sub-runbook extraction

### Phase 2: Pattern Identification
- Identify common patterns across runbooks
- Extract to common/ directory
- Update runbooks to use WikiLinks

### Phase 3: Optimization
- Consolidate similar patterns
- Create parameterized sub-runbooks
- Optimize for token efficiency

### Phase 4: Mature State
- Most logic in sub-runbooks
- Detection runbooks primarily WikiLink includes
- High reusability and maintainability

## Integration with Alert-Planner

The alert-planner skill uses this structure to:

1. **Locate runbooks:** Match alert to runbook via metadata
2. **Resolve includes:** Expand WikiLink includes (`![[path.md]]`)
3. **Apply parameters:** Substitute variables
4. **Generate workflow:** Convert to Tasks and Workflows

## Validation

### Structure Validation
- Correct directory placement
- Valid file naming
- Proper metadata fields

### Content Validation
- WikiLink paths exist
- No circular references
- Required patterns included

### Use validation script:
```bash
python scripts/validate_repository.py ../runbooks-y
```
