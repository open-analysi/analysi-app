# Alert Context Generation (Alert Enrichment)
# Generates concise, LLM-ready context summaries from alerts for downstream AI analysis
# Enriches alerts with structured context information under enrichments["alert_context_generation"]

# Input is the alert directly
alert = input

# Build context prompt for LLM using the entire alert as JSON
# This is defensive - works with any alert regardless of which fields are present
context_prompt = """Generate a concise alert context summary (maximum 300 characters) for AI-powered security analysis.

The alert data is provided in JSON format below. Extract the most critical information to create a single paragraph that captures the alert's intent and context for further investigation.

Alert Data:
-------
${alert|json}
-------

**Requirements:**
- Maximum 300 characters
- Include severity level if present
- Mention if action was blocked/allowed/detected (if present)
- Identify affected entity and threat source (if present)
- Capture the essence of what security event occurred
- DO NOT include recommendations or next steps (analysis only)

Provide a single paragraph that captures the alert's context."""

# Generate context using LLM
alert_context_summary = llm_run(context_prompt)

# Build enrichment structure
enrichment_data = {
    "data_source": "Alert Context Generator",
    "ai_analysis": alert_context_summary
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
