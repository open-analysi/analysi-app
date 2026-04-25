# Example 1: SQL Injection Exact Match (VERY HIGH Confidence)

This example demonstrates a perfect exact match scenario where the alert's detection rule exactly matches an existing runbook.

## Files

- **alert.json** - Input OCSF alert
- **matching-report.json** - Output matching report
- **matched-runbook.md** - Copy of matched runbook (empty here for demo)

## Input

A SQL injection alert from a WAF:
- Detection Rule: "Possible SQL Injection Payload Detected"
- Alert Type: "Web Attack"
- Subcategory: "SQL Injection"
- Source Category: "WAF"
- MITRE Tactics: T1190, T1059

## Expected Output

**Confidence:** VERY HIGH
**Score:** 170 points
- Exact detection rule match: 100 points
- Subcategory match (SQL Injection): 40 points
- Source category match (WAF): 30 points

**Decision:** matched
**Matched Runbook:** `runbooks-repository/sql-injection-detection.md`

## Why VERY HIGH Confidence?

The alert's detection rule "Possible SQL Injection Payload Detected" exactly matches the runbook's detection rule, resulting in an automatic 100-point exact match bonus. Combined with matching subcategory and source category, this produces a VERY HIGH confidence match requiring no composition.

## Usage

This example can be used to test the runbook-match-agent:

```bash
# Run the agent with this example alert
claude-code /agents runbook-match-agent < examples/example-1/alert.json
```

The agent should return the matched runbook with VERY HIGH confidence and no retrospective (since it's a perfect match).
