### Final Analysis ★
- **Sequential:** Must run in order

#### Detailed Analysis ★
- **Action:** Comprehensive technical synthesis of the investigation
- **Depends On:** All prior steps
- **Pattern:** threat_synthesis
- **Input:** ALL outputs
- **Focus:** Complete attack chain analysis, evidence correlation, threat assessment
- **Output:** detailed_analysis

#### Disposition & Summary ★
- **Parallel:** Yes
- **Depends On:** Detailed Analysis
- **Actions:**
  - Determine verdict (TP/FP/Benign) with confidence score
  - Generate executive summary (128 chars max)
- **Pattern:** impact_assessment
- **Input:** outputs.detailed_analysis
- **Outputs:**
  - disposition: {verdict: "TP|FP|Benign", confidence: 0.0-1.0, escalate: true|false}
  - summary: "Attack from ${get_src_ip(alert)} - [successful|unsuccessful] - [impact description]"
