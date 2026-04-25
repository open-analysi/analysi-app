---
# REQUIRED - Alert Classification
detection_rule: [Exact detection rule name]
alert_type: [Broad category: Web Attack|Brute Force|Phishing|etc]
subcategory: [Specific attack: SQL Injection|XSS|IDOR|Command Injection|etc]
source_category: [OCSF source category: WAF|EDR|Identity|etc]

# REQUIRED - Threat Context
mitre_tactics: [T####, T####]

# REQUIRED - Integration Dependencies
integrations_required: [integration1, integration2]
integrations_optional: [integration3, integration4]

# OPTIONAL - Metadata
version: 1.0.0
last_updated: YYYY-MM-DD
author: [team-name]
---

# [Detection Rule Name] Investigation Runbook

## Steps

### 1. Alert Understanding & Initial Assessment ★
- **Action:** Analyze alert and form investigation hypotheses
- **Pattern:** llm_analysis
- **Input:** [relevant OCSF alert fields]
- **Outputs:**
  - context_summary: Human-readable alert summary
  - investigation_hypotheses: [List of theories to investigate]

### 2. Supporting Evidence Collection ★
- **Purpose:** Collect SIEM data to validate hypotheses
- **Parallel:** Yes

#### 2a. [Evidence Type 1] ★
- **Action:** [What to retrieve]
- **Pattern:** integration_query
- **Integration:** splunk
- **Query:** `[Splunk query with ${variables}]`
- **Output:** [output_key]

#### 2b. [Evidence Type 2] ★
- **Action:** [What to retrieve]
- **Pattern:** integration_query
- **Integration:** splunk
- **Query:** `[Splunk query]`
- **Output:** [output_key]

### 3. [Analysis Step Name]
- **Action:** [Analysis action]
- **Pattern:** llm_analysis
- **Input:** [enrichment fields to analyze]
- **Focus:** [What to look for]
- **Output:** [output_key]

### 4. [Enrichment Step Name]
- **Parallel:** Yes
- **Optional:** [If applicable]

#### 4a. [Enrichment Source 1]
- **Action:** [Enrichment action]
- **Pattern:** integration_query
- **Integration:** [integration_name]
- **Condition:** IF [condition]
- **Fields:** [fields_to_enrich]
- **Output:** [output_key]

### 5. Hypothesis Validation ★
- **Action:** Match evidence against initial hypotheses
- **Pattern:** llm_analysis
- **Input:** [All relevant enrichments]
- **Output:** validated_hypothesis

### 6. Impact Assessment
- **Action:** Determine actual and potential impact
- **Pattern:** llm_analysis
- **Input:** [validated hypothesis and evidence]
- **Focus:** [Impact areas to assess]
- **Output:** impact_assessment

### 7. Final Analysis ★
- **Sequential:** Must run in order

#### 7a. Detailed Analysis ★
- **Action:** Comprehensive technical synthesis
- **Pattern:** llm_synthesis
- **Input:** ALL enrichments
- **Output:** detailed_analysis

#### 7b. Disposition & Summary ★
- **Parallel:** Yes
- **Actions:**
  - Determine verdict (TP/FP/Benign) with confidence score
  - Generate executive summary (128 chars max)
- **Pattern:** llm_analysis
- **Input:** enrichments.detailed_analysis
- **Outputs:**
  - disposition: {verdict: "[TP|FP|Benign]", confidence: 0.XX, escalate: [true|false]}
  - summary: "[Brief summary with ${variables}]"

## Conditional Logic

### Branch: [Condition Name]
- **Condition:** [boolean expression using enrichment fields]
- **Additional Steps:**
  - [Step 1]
  - [Step 2]
- **Escalation:** [If applicable]

### Branch: [Fast Track Name]
- **Condition:** [boolean expression]
- **Fast Track:** [Skip to disposition with specific verdict]

---

<!-- Template Usage Notes:

1. Replace all bracketed placeholders with actual values
2. Mark critical steps with ★
3. Remove optional sections if not needed
4. Add more steps as needed for the specific detection
5. Ensure all ${variables} reference actual OCSF fields
6. Keep total runbook under 800 tokens
7. Use WikiLinks for common patterns when applicable

Common Patterns to Consider Including:
- ![[common/universal/alert-understanding.md]]
- ![[common/universal/final-analysis-trio.md]]
- ![[common/by_source/waf-siem-evidence.md]]
- ![[common/evidence/threat-intel-enrichment.md]]

-->
