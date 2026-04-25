### 1. Alert Understanding & Initial Assessment ★
- **Action:** Analyze alert and form investigation hypotheses
- **Pattern:** hypothesis_formation
- **Input:** finding_info.title, severity, get_src_ip(alert), get_dst_ip(alert), get_url(alert), get_http_method(alert), get_user_agent(alert), finding_info.desc
- **Outputs:**
  - context_summary: Human-readable alert summary
  - investigation_hypotheses: List of theories to investigate
  - key_observables: Key indicators from the alert
