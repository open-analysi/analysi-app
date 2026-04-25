# Runbook Quality Guide

## The #1 Quality Criterion: Generic Scope

**A runbook must handle ALL alerts from a detection rule, not just one example.**

Before evaluating any other quality aspect, verify:
- ✅ Built for the **detection rule**, not the specific alert instance
- ✅ Covers both TP and FP scenarios with appropriate investigation paths
- ✅ Doesn't over-fit to obvious characteristics of the example (e.g., obvious scanner → still check for targeted attacks)
- ✅ Would work for the next 100 alerts from this same rule

**If the runbook only handles the example case, it fails regardless of other qualities.**

See `SKILL.md` → "Runbook Scope & Definition of Done" for the full principle.

---

## What Makes a Great Runbook

### 🎯 Characteristics of Excellent Runbooks

#### 1. **Hypothesis-Driven Investigation**
✅ **GOOD:** Specific, testable hypotheses
```markdown
- investigation_hypotheses: ["Automated scanner probing for vulnerabilities", "Targeted exploitation attempt", "Security assessment tool", "Successful data extraction"]
```

❌ **BAD:** Vague, untestable hypotheses
```markdown
- investigation_hypotheses: ["Something bad happened", "Possible attack", "Security issue"]
```

#### 2. **Evidence Validates Hypotheses**
✅ **GOOD:** Each evidence step maps to validating specific hypotheses
```markdown
### 2a. Attack Pattern Analysis ★
- **Action:** Find all requests from source to identify if automated or manual
- **Purpose:** Validate hypothesis: "Automated scanner" vs "Targeted attack"
```

❌ **BAD:** Generic evidence collection without purpose
```markdown
### 2. Get All Logs
- **Action:** Retrieve all available logs
```

#### 3. **Decision Points Are Clear**
✅ **GOOD:** Explicit criteria for decisions
```markdown
- **Decision Points:**
  - Consistent 500 errors + same response size = unsuccessful
  - 200 responses + varying sizes = possible data extraction
  - Single attempt = manual attack
  - 100+ attempts in 5 mins = automated scanner
```

❌ **BAD:** Subjective or missing criteria
```markdown
- **Focus:** Determine if attack was successful based on logs
```

#### 4. **Progressive Refinement**
✅ **GOOD:** Narrow scope progressively
```markdown
Step 1: All requests from IP → Step 2: Only SQL patterns → Step 3: Decode specific payloads
```

❌ **BAD:** Unfocused, scattershot approach
```markdown
Step 1: Get all logs → Step 2: Check everything → Step 3: Look for problems
```

### 🎯 Critical Step Identification (MOST IMPORTANT)

**The #1 quality indicator:** Are critical steps clearly marked with ★?

✅ **GOOD:** 3-5 critical steps clearly identified
```markdown
### 1. Alert Understanding ★         # Must understand the alert
### 2. SIEM Evidence Collection ★    # Core evidence from our environment
### 3. Attack Success Determination ★ # Can't reach verdict without this
### 4. IP Reputation                 # Nice to have enrichment
### 5. Final Analysis ★              # Required SOC output
```

❌ **BAD:** Everything marked critical or nothing marked
```markdown
### 1. Alert Understanding ★
### 2. Check IP ★
### 3. Check Domain ★
### 4. Check Hash ★
### 5. Check User ★
### 6. Check Everything ★
```

**Rule of Thumb:** If you can skip it and still reach a valid verdict, it's NOT critical.

### 📊 Token Efficiency Strategies

#### 1. **Use Sub-Runbooks for Common Patterns**
Instead of repeating 100 tokens of alert understanding in every runbook:
```markdown
![[common/universal/alert-understanding.md]]
```

#### 2. **Terse Attribute Format**
✅ **GOOD:** Concise attributes
```markdown
- **Query:** `index=web src="${get_src_ip(alert)}" | head 20`
- **Output:** recent_requests
```

❌ **BAD:** Verbose descriptions
```markdown
- **Query:** `This query searches the web index for all events where the source IP address matches the attacker's IP address from the alert and returns the first 20 results`
- **Output:** This will store the recent requests made by the attacker
```

#### 3. **Conditional Logic Over Duplication**
✅ **GOOD:** Conditional branches
```markdown
### Branch: High-Volume Attack
- **Condition:** outputs.request_count > 100
- **Additional Steps:** Check for scanner signatures
```

❌ **BAD:** Separate runbooks for each severity/volume

### 🚫 Common Anti-Patterns

#### 1. **The Kitchen Sink**
❌ **Problem:** Collecting every possible piece of data
```markdown
### 2. Collect Everything
- Get all logs from all systems for the past week
- Check every threat intel source
- Query all databases
```
✅ **Solution:** Collect only what validates hypotheses

#### 2. **The Black Box**
❌ **Problem:** No clear connection between evidence and conclusions
```markdown
### 3. Analyze
- **Pattern:** llm_analysis
- **Input:** ALL enrichments
- **Output:** verdict
```
✅ **Solution:** Show reasoning chain explicitly

#### 3. **The Optimist**
❌ **Problem:** Assuming all integrations always work
```markdown
- **Integration:** virustotal  # Required for verdict
```
✅ **Solution:** Mark optional integrations, provide fallbacks

#### 4. **The Time Waster**
❌ **Problem:** Sequential steps that could be parallel
```markdown
### 2. Check IP Reputation (wait)
### 3. Then check domain reputation (wait)
### 4. Then check file hashes (wait)
```
✅ **Solution:** Use parallel execution
```markdown
### 2. Threat Intelligence
- **Parallel:** Yes
#### 2a. IP Reputation
#### 2b. Domain Reputation
#### 2c. File Hash Analysis
```

### 🎨 Hypothesis Quality Rubric

#### Strong Hypotheses Are:
1. **Specific** - "SQL injection via UNION SELECT" not "Database attack"
2. **Testable** - Can be validated with available evidence
3. **Prioritized** - Most likely scenarios first
4. **Complete** - Cover both malicious and benign explanations
5. **Actionable** - Lead to different investigation paths

#### Examples by Alert Type:

**SQL Injection Alert:**
```markdown
investigation_hypotheses: [
  "Automated SQL injection scanner probing",      # Check: request frequency, user-agent
  "Manual exploitation attempt",                  # Check: request sophistication
  "Successful data extraction",                   # Check: response sizes, status codes
  "WAF testing by security team",                 # Check: source IP ownership
  "Application bug causing SQL-like errors"       # Check: legitimate user activity
]
```

**Brute Force Alert:**
```markdown
investigation_hypotheses: [
  "Password spray attack",                        # Check: many users, few passwords
  "Credential stuffing",                          # Check: known breach credentials
  "Single account targeted attack",               # Check: one user, many passwords
  "Legitimate user forgot password",              # Check: user history, source IP
  "Automated bot attack"                          # Check: request patterns, user-agent
]
```

### 📈 Quality Metrics

A runbook should optimize for:

| Metric | Target | Why |
|--------|--------|-----|
| **Critical Steps (★)** | **3-5** | **MOST IMPORTANT: Focus on essential investigation path** |
| Token Count | 500-800 | Efficiency without sacrificing completeness |
| Hypotheses | 3-6 | Balance thoroughness with focus |
| Parallel Steps | >40% | Minimize investigation time |
| Conditional Branches | 2-4 | Handle common scenarios efficiently |
| Integration Dependencies | <3 required | Ensure runbook can execute |

### 🔄 Conditional Logic Best Practices

#### Use Conditional Branches For:
1. **Fast-Track Verdicts** - Skip deep analysis when outcome is clear
2. **Severity Escalation** - Additional steps for critical findings
3. **Integration Availability** - Alternative paths when tools unavailable
4. **Attack Success Forks** - Different paths for successful vs failed attacks

#### Example Structure:
```markdown
### Branch: Confirmed Scanner
- **Condition:** outputs.ip_reputation.scanner_probability > 0.9 AND outputs.request_pattern.automated == true
- **Fast Track:** Mark as "TP - Scanner Activity" without deep payload analysis

### Branch: Successful Exploitation
- **Condition:** outputs.response_analysis.status_200_count > 0 AND outputs.response_sizes.variance > 1000
- **Additional Steps:**
  - Immediate memory dump
  - Check lateral movement
  - Search for persistence
- **Escalation:** Critical - Immediate response required
```

### ✅ Runbook Review Checklist

Before finalizing a runbook, verify:

- [ ] **GENERIC SCOPE** - Handles ALL alerts from this detection rule, not just the example
- [ ] Covers both TP and FP scenarios appropriately
- [ ] Hypotheses are specific and testable
- [ ] Each evidence step validates specific hypotheses
- [ ] Decision criteria are explicit and objective
- [ ] Parallel execution used where possible
- [ ] Critical steps marked with ★
- [ ] Conditional branches handle common scenarios
- [ ] Token count between 500-800
- [ ] Integration failures handled gracefully
- [ ] Output keys are descriptive and consistent
- [ ] Field references use OCSF paths or helper functions (see `ocsf-field-reference.md`)
