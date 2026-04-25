### Supporting Evidence Collection ★
- **Purpose:** Collect SIEM data to validate hypotheses and identify full attack scope
- **Parallel:** Yes

#### SIEM Event Retrieval ★
- **Action:** Retrieve all HTTP requests from attacker IP to identify attack pattern
- **Purpose:** Validates attack progression and scope
- **Pattern:** integration_query
- **Integration:** siem
- **Fields:** get_src_ip(alert), get_dst_ip(alert)
- **Output:** http_events

#### Response Pattern Analysis ★
- **Action:** Analyze HTTP response patterns to detect successful exploitation
- **Purpose:** Validates attack success vs failure
- **Pattern:** integration_query
- **Integration:** siem
- **Focus:** Response sizes, status codes, patterns indicating exploitation success
- **Fields:** get_src_ip(alert)
- **Output:** response_patterns
