# Runbook Composition Guide

This guide provides concrete strategies for composing new runbooks when exact matches aren't available.

## CRITICAL: Compose for the Rule, Not the Alert

**The example alert is just ONE INSTANCE.** When composing a runbook:

- Build for the **detection rule's full scope**, not just the example case
- Same detection rule = same TTPs = similar investigation steps across all instances
- Even if the example looks like an obvious FP, include full investigation paths for TPs
- The runbook must handle ANY alert from this rule, not just the one in front of you

**Definition of Done:** A composed runbook that handles the current alert AND all future alerts from the same detection rule.

See `SKILL.md` → "Runbook Scope & Definition of Done" for complete guidance.

## Composition Decision Tree

```
1. Has exact match with comprehensive runbook? → Use as-is (VERY HIGH confidence)
   ↳ No composition needed

2. Has exact match but sparse? → Enhance it (HIGH confidence)
   ↳ Apply formatting rules below

3. Has similar attack in same family? → Adapt it (HIGH confidence)
   ↳ Apply formatting rules below

4. Has 2+ relevant matches (score 40+)? → Blend them (MEDIUM confidence)
   ↳ Apply formatting rules below

5. Has 1 moderate match (score 20-40)? → Use as skeleton (LOW confidence)
   ↳ Apply formatting rules below
   ↳ LOAD cybersecurity-analyst for patterns

6. No good matches? → Build from universals (VERY LOW confidence)
   ↳ Apply formatting rules below
   ↳ LOAD cybersecurity-analyst for patterns
```

## When to Load Complementary Skills

### Composition Formatting Quality Checklist

**When composing or adapting runbooks, ensure:**
- ✅ Proper YAML frontmatter structure
- ✅ Critical steps correctly marked with ★
- ✅ Valid WikiLink usage (`![[path.md]]`)
- ✅ Pattern-to-Cy mapping consistency
- ✅ Runbook completeness
- ✅ DRY principles with sub-runbooks

**The runbooks-manager skill provides built-in references for:**
- Format specifications (`references/building/format-specification.md`)
- Sub-runbook patterns (`references/building/sub-runbook-patterns.md`)
- Quality guidelines (`references/building/quality-guide.md`)
- Data flow specifications (`references/building/data-flow-specification.md`)

### Load `cybersecurity-analyst` Skill When:
- **Confidence is LOW or VERY LOW** - Need expert investigation patterns
- **Novel attack type** - No similar patterns in repository
- **Missing investigation steps** - Need to fill gaps in composed runbook
- **Complex multi-stage attacks** - Need advanced correlation guidance

**How it helps:**
- Provides structured investigation workflows by alert type
- Offers IOC analysis patterns and threat hunting queries
- Supplies escalation criteria and severity assessment
- Gives context-specific investigation focus areas

## Composition Patterns

### Pattern 1: Same Attack Family Adaptation
**When:** Different variant of same attack type (e.g., PostgreSQL vs MySQL injection)
**Strategy:**
- Keep the investigation flow identical
- Adapt only the specific technical details
- Maintain all critical steps (★)
- Confidence: HIGH

**Example:**
```markdown
# Original: sql-injection-detection.md (MySQL)
# Adapting for: PostgreSQL Injection

Keep: Investigation structure, SIEM queries, impact assessment
Adapt: Payload patterns, database-specific syntax
```

### Pattern 2: Multi-Source Blending
**When:** Multiple relevant matches with different strengths
**Strategy:**
- Take investigation flow from highest scoring match
- Add enrichment steps from other matches
- Combine evidence collection patterns
- Confidence: MEDIUM

**Example:**
```markdown
# Composing: GraphQL API Attack
# Sources: sql-injection.md (45), api-abuse.md (42), command-injection.md (38)

From sql-injection.md:
- SIEM query structure
- Payload analysis approach

From api-abuse.md:
- Rate limiting checks
- API-specific headers analysis

From command-injection.md:
- Command execution indicators
```

### Pattern 3: Category-Based Assembly
**When:** Same category but different specifics
**Strategy:**
- Use category template (e.g., all web attacks)
- Add specific detection patterns
- Include category-standard evidence collection
- Confidence: MEDIUM to LOW

**Categories and Their Patterns:**
```
Web Application Attacks:
├── Always include: WAF logs, HTTP analysis
├── Common steps: Payload decode, parameter analysis
└── Standard checks: Response sizes, status codes

Authentication Attacks:
├── Always include: Failed login analysis
├── Common steps: Account enumeration, timing
└── Standard checks: Lockout patterns, geo-anomalies

CVE Exploitations:
├── Always include: Vendor advisories, patch status
├── Common steps: Version identification, exploit indicators
└── Standard checks: IOCs from threat intel
```

### Pattern 4: Minimal Scaffold (Skills Required)
**When:** Only weak matches available
**Strategy:**
- Start with universal components only
- **LOAD cybersecurity-analyst skill** for investigation patterns
- Add basic evidence collection for source type
- Include generic threat intel enrichment
- Mark as requiring analyst customization
- Confidence: VERY LOW

**Example with skill integration:**
```markdown
# Step 1: Load complementary skills if needed
Load: cybersecurity-analyst  # For investigation workflows (LOW/VERY LOW confidence)

# Step 2: Get investigation pattern from cybersecurity-analyst
For "Unknown API Attack":
- Use Web Application Alert patterns
- Apply API-specific investigation focus
- Include authentication analysis steps

# Step 3: Format using built-in references
- Add proper YAML frontmatter (see references/building/format-specification.md)
- Mark critical steps with ★ (typically 3-5 per runbook)
- Validate WikiLink syntax (see references/building/sub-runbook-patterns.md)
```

## Composition Rules

### ALWAYS Include
1. **Universal Components**
   ```markdown
   ![[common/universal/alert-understanding.md]]
   ![[common/universal/final-analysis-trio.md]]
   ```

2. **Source-Specific Evidence**
   - WAF alerts → WAF SIEM evidence collection
   - EDR alerts → Endpoint telemetry
   - Email alerts → Email header analysis

3. **Threat Intelligence**
   ```markdown
   ![[common/evidence/threat-intel-enrichment.md]]
   ```

### NEVER Do
1. **Don't invent queries** - Only include queries that exist in source runbooks
2. **Don't skip critical steps** - All ★ steps from source runbooks should be considered
3. **Don't mix incompatible patterns** - Email investigation steps don't belong in WAF runbooks
4. **Don't hide uncertainty** - Always document gaps and low confidence areas

## Blending Priority Matrix

When selecting which runbook contributes which sections:

| Section | Priority Source |
|---------|-----------------|
| Investigation Flow | Highest total score |
| SIEM Queries | Same source_category |
| Payload Analysis | Same attack_type |
| Threat Intel | Most similar attack |
| Impact Assessment | Same severity level |
| Mitigations | Same technology stack |

## Confidence Factors in Composition

### Increases Confidence:
- Multiple runbooks with similar patterns (consensus)
- Same source category (evidence compatibility)
- Overlapping MITRE tactics (similar adversary behavior)
- Recent runbooks (up-to-date patterns)

### Decreases Confidence:
- Conflicting investigation approaches
- Different source categories
- No attack type similarity
- Sparse source runbooks
- Many gaps identified

## Output Template for Composed Runbook

```yaml
---
# COMPOSED RUNBOOK - REQUIRES REVIEW
detection_rule: [From alert]
alert_type: [From alert]
source_category: [From alert]
composition_metadata:
  confidence: MEDIUM
  primary_source: sql-injection-detection.md
  blended_from:
    - file: sql-injection-detection.md
      sections: [2, 3, 4]
      reason: "Same source category, similar attack"
    - file: api-abuse-detection.md
      sections: [5]
      reason: "API-specific patterns"
  gaps_identified:
    - "No GraphQL-specific payload patterns"
    - "Rate limiting thresholds uncertain"
  review_required: true
---

# Investigation Steps
[Composed content with provenance notes]
```

## Composition Quality Checklist

Before finalizing a composed runbook:

- [ ] Universal components included?
- [ ] Source-specific evidence collection present?
- [ ] Critical steps (★) preserved from sources?
- [ ] Provenance documented for each section?
- [ ] Gaps and uncertainties noted?
- [ ] Confidence level justified?
- [ ] Investigation flow logical?
- [ ] No incompatible patterns mixed?

## Evolution Through Feedback

Track composition success:
1. Note which composed runbooks analysts actually use
2. Identify patterns that work well together
3. Document anti-patterns (what doesn't blend well)
4. Update weights based on composition success rates
5. Convert successful compositions into permanent runbooks
