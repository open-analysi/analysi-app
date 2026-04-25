# URL Decoder and SQL Injection Analyzer
# Decodes URL-encoded payloads and analyzes for SQL injection patterns

# Input is the alert directly
alert = input

# Extract context for LLM (use reusable pattern with multiple fallbacks)
# Try alert_context enrichment first, then rule_name, then title
enrichments = alert.enrichments ?? {}
alert_context_enrichment = enrichments.alert_context_generation ?? null
alert_context = alert_context_enrichment.ai_analysis ??
                alert.rule_name ??
                alert.title ??
                "unknown alert"

# Extract web_info with null-safe access
web_info = alert.web_info ?? null
if (web_info == null) {
    return alert
}

# Extract URL
url = web_info.url ?? ""
if (url == "") {
    return alert
}

# Decode the URL using native Cy function
decoded_url = url_decode(url)

# Build LLM prompt using triple-quoted string with interpolation
prompt = """You are analyzing a security alert for SQL injection attacks.

Alert Context: ${alert_context}

Original URL: ${url}
Decoded URL: ${decoded_url}

Analyze the decoded URL and identify:
1. SQL injection patterns (e.g., OR 1=1, comment injection, quote manipulation)
2. Attack type (Classic, Blind, Time-based, Boolean-based)
3. What the payload attempts to do
4. Risk level (low, medium, high) and sophistication

Provide a concise 3-4 sentence assessment."""

# Use LLM to analyze
analysis_text = llm_run(prompt)

# Extract key information using regex patterns
analysis_lower = lowercase(analysis_text)

# Check for SQL injection detection using regex
sql_injection_detected = regex_match(".*sql.*(injection|inject).*", analysis_lower)

# Determine risk level from analysis text using regex
risk_level = "medium"
if (regex_match(".*(high risk|critical|severe).*", analysis_lower)) {
    risk_level = "high"
} elif (regex_match(".*(low risk|benign|unsuccessful|blocked|failed).*", analysis_lower)) {
    risk_level = "low"
}

# Build enrichment data
enrichment_data = {
    "original_url": url,
    "decoded_url": decoded_url,
    "sql_injection_detected": sql_injection_detected,
    "risk_level": risk_level,
    "ai_analysis": analysis_text
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
