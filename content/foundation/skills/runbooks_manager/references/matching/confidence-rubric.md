# Confidence Rubric for Runbook Matching

This document defines how to assign confidence levels. The key decision boundary is simple: **exact `detection_rule` match = matched, everything else = composed.**

## Decision Boundary

```
alert.detection_rule == runbook.detection_rule?
  → YES: "matched" — confidence is VERY HIGH or HIGH
  → NO:  "composed" — confidence is HIGH, MEDIUM, LOW, or VERY LOW
```

Scores from the matching algorithm are used to **rank candidates for composition**, not to decide match vs compose.

## Confidence Levels

### VERY HIGH (matched only)
**When to assign:**
- Exact detection rule match AND the matched runbook is comprehensive (has multiple includes, 5+ investigation steps)
- The runbook was specifically created for this exact detection rule

**What this means for the analyst:**
- Use the runbook as-is with high trust
- No adaptation needed
- Investigation steps are battle-tested for this exact scenario

### HIGH (matched or composed)
**When to assign:**
- Exact detection rule match BUT the runbook is relatively sparse (fewer steps, minimal includes)
- OR: Composed runbook where a closely matching `by_type/` pattern exists AND the alert's attack type is well-represented in the building blocks

**What this means for the analyst:**
- Runbook is highly relevant and trustworthy
- If composed, the building blocks are proven patterns — minor review recommended
- Core investigation flow is correct

### MEDIUM (composed only)
**When to assign:**
- Composed runbook assembled from multiple relevant `by_type/` patterns
- Good overlap in attack category and source type
- Building blocks cover most of the investigation but some gaps may exist

**What this means for the analyst:**
- Review the composed runbook before use
- Core patterns are sound but specific details may need adjustment
- Investigation structure is reliable

### LOW (composed only)
**When to assign:**
- Composed runbook with limited pattern coverage — only one `by_type/` pattern partially applies
- Relying heavily on universal components with minimal attack-specific guidance

**What this means for the analyst:**
- Treat as a starting template requiring significant review
- May need to add investigation steps specific to the alert
- Universal steps are reliable but attack-specific steps need validation

### VERY LOW (composed only)
**When to assign:**
- No relevant `by_type/` patterns exist for this alert type
- Composed entirely from universal components (alert understanding, final analysis, threat intel)
- Alert type is novel with no similar patterns in the repository

**What this means for the analyst:**
- This is a basic framework requiring substantial customization
- Consider this a creative starting point, not a proven runbook
- Recommend creating a proper runbook after investigation completes

## Contextual Factors to Consider

Beyond raw scores, consider these factors when assigning confidence:

1. **Runbook Completeness**: Does the matched runbook have comprehensive steps, or is it a skeleton?

2. **Attack Similarity**: Are we matching within the same attack family (injection attacks) or across different types?

3. **Source Alignment**: Does the detection source match? WAF runbooks work best for WAF alerts.

4. **Composition Quality**: When blending runbooks, how well do the patterns align?

5. **Coverage Gaps**: Are critical investigation areas missing from available runbooks?

## Examples

### Example 1: VERY HIGH Confidence
```
Alert: "Possible SQL Injection Payload Detected"
Match: sql-injection-detection.md (exact match)
Runbook has: 8 steps, 4 includes, proven in production
Confidence: VERY HIGH - "Exact match with comprehensive runbook"
```

### Example 2: HIGH Confidence
```
Alert: "PostgreSQL Injection Attempt"
Match: sql-injection-detection.md (score: 75)
Similar attack type, same source category
Confidence: HIGH - "Very similar SQL injection variant"
```

### Example 3: MEDIUM Confidence
```
Alert: "GraphQL Query Manipulation"
Matches: sql-injection (45), api-abuse (42), command-injection (38)
Composing from 3 relevant patterns
Confidence: MEDIUM - "Composed from multiple relevant patterns"
```

### Example 4: LOW Confidence
```
Alert: "Unusual API Behavior Detected"
Match: api-abuse-detection.md (score: 25)
Only one weak match
Confidence: LOW - "Single moderate match, significant adaptation needed"
```

### Example 5: VERY LOW Confidence
```
Alert: "Quantum Key Distribution Attack"
Matches: None above 15
Confidence: VERY LOW - "Novel attack type, creative composition required"
```

## Confidence Communication

When presenting confidence to users:

- Always explain WHY the confidence level was assigned
- Note what aspects are reliable vs uncertain
- Suggest specific areas that may need review
- Document which runbooks contributed to composition
