# SOC165 - SQL Injection Workflow Example

This example demonstrates workflow creation from a standardized runbook for a SQL injection web attack case.

## Source Runbook

This workflow was created from:

```
../runbooks-y/runbooks-repository/sql-injection-detection.md
```

The runbook includes:
- Investigation steps with criticality markers (★)
- Integration requirements (siem, threat_intel)
- Pattern mappings (payload_analysis, integration_query, etc.)
- Alert example from SOC165 for testing

## Example Files

### alert.json

The `alert.json` file in this directory shows the OCSF Detection Finding alert example included in the runbook's `alert_examples` field. This alert is used for testing the workflow.

### results.md

Documents the complete workflow creation process:
- Tasks identified from runbook steps
- Existing tasks reused
- New tasks created
- Workflow composition
- Integration availability

## Workflow Overview

The workflow follows the mandatory structure:
1. **alert_context_generation** (prefix)
2. **Investigation tasks** (from runbook steps)
   - URL payload decoding and analysis
   - IP reputation checks (VirusTotal, AbuseIPDB)
   - SIEM evidence collection
   - Attack success determination
3. **Mandatory triad** (suffix)
   - Detailed analysis
   - Disposition determination
   - Summary generation

## Case Summary

- **SOC ID**: soc165 (runbook source)
- **Detection Rule**: Possible SQL Injection Payload Detected
- **Attack Type**: SQL Injection
- **Severity**: High
- **Source IP**: 91.234.56.17
- **Target**: WebServer1001
- **Disposition**: True Positive - Attack Blocked
- **Key IOCs**: Malicious IP with SQL injection payload in URL

## Related Files

- **Source runbook**: `../runbooks-y/runbooks-repository/sql-injection-detection.md`
- **Alert example**: `alert.json` (from runbook alert_examples field)
- **Workflow results**: `results.md` (task breakdown and composition)
- **Skill documentation**: `../../SKILL.md` (runbook-to-workflow process)
