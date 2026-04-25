# ProxyNotShell Payload Decoder and Analyzer
# Purpose: Decode URL-encoded payloads and identify CVE-2022-41040/CVE-2022-41082 indicators

# Extract URL from multiple sources with fallbacks
raw_url = get_url(input) ?? ""
if (raw_url == "") {
    # Fallback to Splunk enrichment if available
    splunk_urls = input.enrichments.splunk_supporting_evidence.request_urls ?? []
    if (len(splunk_urls) > 0) {
        raw_url = splunk_urls[0]
    }
}

# Get alert context for LLM reasoning
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                input.title ??
                "ProxyNotShell exploitation attempt"

# LLM-based URL decoding and pattern analysis
analysis_text = llm_run(
    prompt="""You are analyzing a URL for ProxyNotShell attack indicators.

Alert Context: ${alert_context}
URL to analyze: ${raw_url}

ProxyNotShell Attack Patterns:
1. CVE-2022-41040 (SSRF): /autodiscover/autodiscover.json?@external-domain
2. CVE-2022-41082 (RCE): FooProtocol=Powershell or Protocol parameters

Analyze this URL and return ONLY valid JSON (no markdown, no code blocks):
{
  "decoded_payload": "URL-decoded version of the payload",
  "ssrf_indicators": {
    "found": true,
    "pattern": "describe SSRF pattern if found",
    "cve": "CVE-2022-41040"
  },
  "powershell_indicators": {
    "found": false,
    "parameters": [],
    "cve": "CVE-2022-41082"
  },
  "external_domains": [],
  "scanner_detection": {
    "is_scanner": false,
    "user_agent": "N/A"
  },
  "decision_points": ["Summary of findings"]
}

CRITICAL: Return ONLY the JSON object above, no other text."""
)

# Parse LLM response with error handling
try {
    analysis = from_json(analysis_text)
} catch (e) {
    # Fallback if LLM didn't return valid JSON
    analysis = {
        "decoded_payload": raw_url,
        "ssrf_indicators": {"found": False, "pattern": "parse_error", "cve": "CVE-2022-41040"},
        "powershell_indicators": {"found": False, "parameters": [], "cve": "CVE-2022-41082"},
        "external_domains": [],
        "scanner_detection": {"is_scanner": False, "user_agent": "N/A"},
        "decision_points": ["LLM JSON parse error - manual review required"]
    }
}

# Build enrichment
enrichment = {
    "raw_url": raw_url,
    "decoded_payload": analysis.decoded_payload,
    "ssrf_indicators": analysis.ssrf_indicators,
    "powershell_indicators": analysis.powershell_indicators,
    "external_domains": analysis.external_domains,
    "scanner_detection": analysis.scanner_detection,
    "decision_points": analysis.decision_points,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
