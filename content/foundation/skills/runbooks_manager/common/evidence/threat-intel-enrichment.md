### Threat Intelligence Enrichment
- **Parallel:** Yes
- **Optional:** Both sources can fail gracefully

#### IP Reputation Check
- **Action:** Check attacker IP reputation in threat intelligence sources
- **Purpose:** Validates threat actor profile and attribution
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** ip_reputation

#### IP Abuse History & Geolocation
- **Action:** Check IP abuse history and geographic location from threat databases
- **Purpose:** Context for attacker origin and history
- **Pattern:** integration_query
- **Integration:** threat_intel
- **Condition:** IF threat_intel configured
- **Fields:** get_src_ip(alert)
- **Output:** geo_abuse_data
