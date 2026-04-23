### Command Injection Payload & Technique Analysis ★
- **Action:** Extract injected commands and analyze attack progression
- **Purpose:** Validates: "Reconnaissance" vs "Targeted data theft"
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Commands in POST parameters (whoami, ls, uname, cat, etc.), command types (reconnaissance vs exploitation), command chaining, privilege escalation attempts, sensitive file access patterns
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** cmdi_payload_analysis
- **Decision Points:**
  - Single command type → Basic testing
  - Progressive command complexity → Sophisticated attacker
  - Sensitive files targeted (passwd, shadow) → Credential theft attempt
  - System commands only (whoami, uname, ls) → Reconnaissance phase

### Command Execution Verification ★
- **Action:** Verify if commands were executed on the endpoint
- **Depends On:** Command Injection Payload & Technique Analysis
- **Pattern:** integration_query
- **Integration:** edr
- **Focus:** Command execution history on target host matching injected commands
- **Fields:** get_primary_device(alert), get_dst_ip(alert)
- **Output:** cmdi_execution_evidence
- **Decision Points:**
  - Commands match injection attempts → Successful execution confirmed
  - No matching commands → Blocked at application/WAF level
  - Partial matches → Some commands succeeded
  - Commands executed as root → Full system compromise
