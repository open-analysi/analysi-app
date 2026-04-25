# Runbook Matcher Examples

End-to-end examples demonstrating the runbook matching workflow.

## Available Examples

### Example 1: SQL Injection Exact Match (VERY HIGH Confidence)

**Directory:** `example-1/`

Demonstrates a perfect exact match scenario where the alert detection rule exactly matches an existing runbook.

- **Input:** SQL injection alert from WAF
- **Confidence:** VERY HIGH (170 points)
- **Decision:** matched
- **Composition:** Not needed
- **Retrospective:** Not needed

See `example-1/README.md` for details.

## Example Structure

Each example directory contains:
- `alert.json` - Input OCSF alert
- `matching-report.json` - Output matching report
- `matched-runbook.md` - Copy of matched runbook (or composed-runbook.md for compositions)
- `README.md` - Explanation and expected results (**for testing/documentation only**)

**Note:** The README.md file is included in examples for documentation purposes. When the runbook-match-agent runs in production, it should NOT create a README.md file. Agent output should contain only:
1. `matching-report.json`
2. `matched-runbook.md` OR `composed-runbook.md`
3. `retrospective.md` (optional)

## Future Examples

Additional examples to add:
- **Example 2:** Similar but not exact match (MEDIUM confidence, composition required)
- **Example 3:** Novel attack type (LOW confidence, composition with cybersecurity-analyst)
- **Example 4:** CVE-based matching with vendor/year scoring
