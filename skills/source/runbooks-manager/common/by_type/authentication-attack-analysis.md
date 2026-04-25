### Authentication Attempt Analysis ★
- **Action:** Enumerate authentication attempts from source and determine attack pattern
- **Purpose:** Establish attack scope, credential targeting, and success/failure rate
- **Pattern:** integration_query
- **Integration:** siem, identity
- **Fields:** get_src_ip(alert), get_primary_user(alert), get_url(alert), time
- **Focus:** Login attempts to authentication endpoints (count, timing, credentials), credential patterns (single user vs spray, default vs custom), authentication protocol (HTTP POST, SAML, OAuth), failed vs successful attempt ratio
- **Output:** auth_attempt_analysis
- **Decision Points:**
  - `attempt_count < 10` → Low-volume targeted attack or credential stuffing
  - `attempt_count 10-50` → Moderate brute force
  - `attempt_count > 50` → High-volume automated attack
  - Single username with many passwords → Brute force
  - Many usernames with few passwords → Credential spraying
  - Default credentials (admin/admin, root/123456) → Default credential attack

### Authentication Success Determination ★
- **Action:** Check OS and identity provider logs for successful authentication events
- **Purpose:** Determine if attacker gained access — critical for escalation decision
- **Depends On:** Authentication Attempt Analysis
- **Pattern:** integration_query
- **Integration:** siem, identity
- **Fields:** get_src_ip(alert), get_primary_user(alert), get_dst_ip(alert)
- **Focus:** Successful login events, compromised user accounts, MFA status (challenged/passed/bypassed), session creation, timing correlation between attempts and success
- **Output:** auth_success_verdict
- **Decision Points:**
  - `successful_login == true` → Account compromised (CRITICAL — escalate immediately)
  - `successful_login == false AND all rejected` → Attack blocked
  - `MFA challenged AND passed` → Possible MFA phishing or token theft
  - `MFA not challenged` → MFA gap — critical security concern
  - `new device fingerprint + successful login` → High confidence compromise
  - `session_created == true` → Active attacker session — immediate response needed

### Account Compromise Impact Assessment
- **Action:** Assess post-authentication activity and determine compromise scope
- **Depends On:** Authentication Success Determination
- **Condition:** IF outputs.auth_success_verdict.successful_login == true
- **Pattern:** impact_assessment
- **Integration:** edr, identity
- **Fields:** get_primary_user(alert), get_primary_device(alert), get_dst_ip(alert)
- **Focus:** Post-login command execution, lateral movement indicators, persistence mechanisms, data access patterns, privilege escalation, email forwarding rules, OAuth app grants
- **Output:** auth_compromise_assessment
- **Decision Points:**
  - `post_login_commands detected` → Active exploitation in progress
  - `lateral_movement indicators` → Attacker expanding access
  - `privilege_escalation attempted` → Critical system compromise risk
  - `email forwarding rules created` → Business email compromise (BEC)
  - `OAuth apps granted` → Persistent access established
  - `no post_login activity` → Credentials compromised but not yet exploited
