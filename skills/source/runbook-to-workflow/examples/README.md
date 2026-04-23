# Runbook-to-Workflow Examples

This directory contains complete examples of workflows created from standardized runbooks.

## Example Index

### 1. SQL Injection

**Directory:** `sql-injection/`

**Source Runbook:** `../runbooks-y/runbooks-repository/sql-injection-detection.md`

**Demonstrates:**
- Runbook parsing and step extraction
- Mapping runbook patterns to tasks (payload_analysis, integration_query)
- Parallel execution opportunities (threat intel + payload analysis)
- Alert example usage from runbook for testing
- Complete workflow composition

**Key Files:**
- `alert.json` - OCSF alert from runbook alert_examples
- `results.md` - Complete task breakdown and workflow composition
- `README.md` - Example overview

### 2. ProxyNotShell CVE-2022-41082 (SOC175)

**Directory:** `proxynotshell-cve-2022-41082/`

**Source Runbook:** `../runbooks-y/runbooks-repository/proxynotshell-cve-2022-41082.md`

**Demonstrates:**
- CVE-based investigation workflow
- EDR integration for Exchange Server process analysis
- Attack relevance assessment with CVE context
- Blocked attack handling and verification
- ProxyNotShell-specific attack patterns (SSRF + PowerShell RCE)

**Key Files:**
- `alert.json` - OCSF alert from runbook alert_examples (SOC175)
- `source.md` - Original investigation (reference)
- `results.md` - Complete task breakdown and workflow composition
- `README.md` - Example overview

## Example Structure

Each example follows this structure:

```
{example-name}/
├── README.md           # Example overview and usage
├── alert.json          # OCSF alert (from runbook alert_examples)
└── results.md          # Complete workflow creation documentation
```

## Using These Examples

1. **Read the runbook** (if it exists in `../runbooks-y/runbooks-repository/`)
2. **Review the example** to see how runbook steps map to tasks
3. **Study results.md** to understand:
   - How runbook patterns were interpreted
   - Which existing tasks were reused
   - Why new tasks were created
   - How the workflow was composed

## Creating New Examples

When creating a new example:

1. Start with a standardized runbook from `../runbooks-y/runbooks-repository/`
2. Extract alert example from runbook's `alert_examples` field
3. Follow the runbook-to-workflow process
4. Document results showing:
   - Runbook source
   - Task mapping decisions
   - Workflow composition rationale
   - Integration availability
   - Test results with alert example

## See Also

- **runbook-to-workflow SKILL.md** - Complete process documentation
- **../runbooks-y/** - Standardized runbook repository
- **runbook-builder** skill - Runbook format and patterns
