# Runbook Matching Criteria

This document defines the prioritized criteria used for matching OCSF Detection Finding alerts to runbooks. These priorities are intentionally configurable and can be adjusted based on operational experience.

## Current Priority Order (Highest to Lowest)

### 1. Exact Detection Rule Match (Weight: 100)
- **Rationale**: If the detection rule exactly matches, this is the most specific and reliable match
- **Example**: Alert "SQL Injection Detection" → Runbook "sql-injection-detection.md"
- **Future Consideration**: May want to handle minor variations (case, punctuation)

### 2. Subcategory Similarity (Weight: 40 for exact, 25 for similar)
- **Rationale**: Attacks of the same subcategory follow similar investigation patterns
- **Implementation**: `subcategory_match` (exact) and `subcategory_similar` (same family) in `match_scorer.py`
- **Priority**: We intentionally prioritize subcategory over other factors because:
  - Web attacks have fairly similar investigation flows
  - Attack patterns are more important than where they're detected
- **Categories**:
  - **Injection attacks**: SQL, NoSQL, Command, LDAP, XPath injection
  - **XSS attacks**: Reflected, Stored, DOM-based XSS
  - **Authentication attacks**: Brute force, credential stuffing, bypass
  - **File inclusion**: LFI, RFI, path traversal
  - **Access control**: IDOR, privilege escalation, authorization bypass

### 3. Broad Alert Type Match (Weight: 20)
- **Rationale**: Broad category like "Web Attack" or "Brute Force" indicates general investigation approach
- **Distinction**: This is separate from subcategory (Section 2). Subcategory matches specific attack types (SQL Injection, XSS), while alert type groups them into broad families.
- **Implementation**: `alert_type_match` in `match_scorer.py`

### 4. CVE-Specific Matching (Weight: 35 for vendor, 10 for year)
- **Rationale**: CVEs from the same vendor/product share exploitation patterns
- **Example**: Two Microsoft Exchange CVEs likely need similar investigation
- **Future Enhancement**: Could add product-level matching

### 5. Source Category Match (Weight: 30)
- **Rationale**: Same detection source means similar log formats and evidence
- **Categories**: WAF, EDR, Identity, Email, Network
- **Note**: Less important than attack type but still significant

### 6. MITRE Tactics Overlap (Weight: 20 per tactic)
- **Rationale**: Overlapping tactics suggest similar adversary behavior
- **Implementation**: Cumulative scoring for multiple overlaps
- **Future Enhancement**: Could weight certain tactics higher (e.g., Initial Access)

### 7. Integration Compatibility (Weight: 15)
- **Rationale**: Runbook is only useful if required integrations are available
- **Future Implementation**: Check if alert's environment has runbook's required tools

## Confidence Levels

**Decision boundary:** Exact `detection_rule` match = "matched". Everything else = "composed".

Scores are used to **rank candidates for composition**, not to decide match vs compose:
- **100+** → Strong candidate for drawing patterns from (exact rule match is handled separately)
- **70-99** → Good candidate — attack-type patterns likely transfer
- **40-69** → Moderate candidate — some patterns applicable
- **20-39** → Weak candidate — limited pattern relevance
- **<20** → Not useful for composition

## Adjusting Priorities

To change matching priorities, modify the `WEIGHTS` dictionary in `scripts/match_scorer.py`:

```python
WEIGHTS = {
    'exact_detection_rule': 100,     # Exact match on detection rule name
    'subcategory_match': 40,         # Same subcategory (e.g., SQL Injection)
    'subcategory_similar': 25,       # Similar subcategory family (e.g., injection)
    'alert_type_match': 20,          # Same broad alert type (e.g., Web Attack)
    'source_category': 30,           # Same source (WAF, EDR, etc.)
    'mitre_overlap': 20,             # Per overlapping MITRE tactic
    'integration_compatibility': 15, # Has required integrations
    'cve_same_vendor': 35,           # Same vendor for CVE attacks
    'cve_same_year': 10,             # Same year for CVE attacks
}
```

## Future Improvements

1. **Machine Learning**: Track which matches analysts actually use
2. **Feedback Loop**: Adjust weights based on success rates
3. **Contextual Matching**: Consider time of day, affected systems
4. **Semantic Similarity**: Use NLP for detection rule similarity
5. **Environment Awareness**: Factor in available integrations
