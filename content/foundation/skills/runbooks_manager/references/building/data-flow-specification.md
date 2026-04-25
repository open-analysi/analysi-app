# Data Flow Specification

## Overview

Clear data flow is CRITICAL for the Analysis AI SOC engine to chain Tasks properly. Every input must have a traceable source, and every output must have a clear consumer.

## Data Flow Rules

### 1. Output Naming Convention

Every step that produces data MUST declare an output key:
```markdown
- **Output:** descriptive_key_name
```

### 2. Input Source Declaration

Every input MUST clearly specify its source using namespaces:

| Source Type | Namespace | Example | Description |
|-------------|-----------|---------|-------------|
| OCSF Field | OCSF path or helper | `get_src_ip(alert)`, `finding_info.title` | From the OCSF Detection Finding event |
| Previous Output | `outputs.` | `outputs.sql_payloads` | From earlier step |
| Sub-runbook Param | `params.` | `params.time_window` | From WikiLinks parameters |
| All Previous | `ALL outputs` | `ALL outputs` | Every prior output |

### 3. Step Dependencies

Make dependencies explicit using a reference format:

```markdown
### 3. Payload Analysis ★
- **Action:** Analyze SQL payloads
- **Depends On:** Step 2b (sql_payloads)  # <-- EXPLICIT DEPENDENCY
- **Input:** outputs.sql_payloads
- **Output:** payload_sophistication
```

## Data Flow Diagram Pattern

For complex runbooks, include a flow diagram:

```
Step 1: Alert Understanding
├── Output: investigation_hypotheses
├── Output: key_observables
└── Output: context_summary
    │
    ├──→ Step 5: Attack Success (uses: investigation_hypotheses)
    ├──→ Step 6: Validation (uses: investigation_hypotheses)
    └──→ Step 8a: Final Analysis (uses: ALL)

Step 2a: Request Frequency
└── Output: request_frequency
    └──→ Step 5: Attack Success (uses: request_frequency)

Step 2b: SQL Payloads
└── Output: sql_payloads
    └──→ Step 3: Payload Analysis (uses: sql_payloads)
```

## Example: Clear Data Flow

### Before (Unclear):
```markdown
### 3. Analyze Payloads
- **Input:** sql_injection_attempts
- **Output:** decoded_analysis
```
❓ Where does `sql_injection_attempts` come from?

### After (Clear):
```markdown
### 3. Analyze Payloads
- **Depends On:** Step 2b
- **Input:** outputs.sql_payloads  # From Step 2b: SQL Pattern Requests
- **Output:** decoded_analysis
```
✅ Source is explicit!

## Step Output Usage Matrix

Track which steps consume which outputs:

| Step | Produces | Consumed By |
|------|----------|-------------|
| 1 | investigation_hypotheses | Steps 5, 6 |
| 1 | key_observables | Step 8a |
| 2a | request_frequency | Step 5 |
| 2b | sql_payloads | Step 3 |
| 3 | payload_sophistication | Steps 5, 6 |
| 4a | ip_reputation | Step 6 |
| 5 | attack_verdict | Steps 6, 7 |
| 6 | validated_hypothesis | Step 7 |
| 7 | impact_assessment | Step 8a |
| 8a | detailed_analysis | Step 8b |

## Integration Query Fields

For integration queries, field access doesn't use ${} in the Fields attribute:

```markdown
### Correct:
- **Fields:** get_src_ip(alert), get_dst_ip(alert)

### Incorrect:
- **Fields:** ${get_src_ip(alert)}, ${get_dst_ip(alert)}
```

But DO use ${} in query strings:
```markdown
- **Query:** `index=web src="${get_src_ip(alert)}"`
```

## Validation Checklist

Before finalizing a runbook:

- [ ] Every step with output has a named Output key
- [ ] Every Input clearly shows its namespace (OCSF path/helper, outputs., params.)
- [ ] Steps that depend on specific prior outputs list "Depends On"
- [ ] No bare field names without namespace
- [ ] Integration Fields use OCSF paths or helper functions without ${}
- [ ] Query strings use ${} for substitution
- [ ] Conditional logic uses outputs. namespace for conditions

## Common Patterns

### Sequential Dependencies
```markdown
### 3. Step Name
- **Depends On:** Step 2
- **Input:** outputs.previous_step_output
```

### Multiple Dependencies
```markdown
### 5. Correlation Step
- **Depends On:** Steps 2a, 2b, 3
- **Input:** outputs.freq, outputs.payloads, outputs.decoded
```

### Conditional Input
```markdown
### 4. Enrichment
- **Input:** outputs.ip_reputation IF available, get_src_ip(alert)
```

### All Prior Outputs
```markdown
### 8a. Final Analysis
- **Depends On:** All prior steps
- **Input:** ALL outputs
```
