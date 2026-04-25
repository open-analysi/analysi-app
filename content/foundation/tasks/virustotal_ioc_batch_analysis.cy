# VirusTotal Batch IOC Analysis (Alert Enrichment)
# Extracts all IOCs from alert and enriches with VirusTotal reputation analysis
# Demonstrates: Multi-IOC batch processing, type-based routing, structured enrichment

# Input is the alert directly
alert = input

# Get IOCs array (safely handles missing key)
iocs = get_observables(alert) ?? []

# Early return if no IOCs to analyze
if (len(iocs) == 0) {
    return alert
}

# Initialize batch results
batch_results = []
total_analyzed = 0
high_risk_count = 0
medium_risk_count = 0
low_risk_count = 0
error_count = 0

# Process each IOC with VirusTotal
for (current_ioc_raw in iocs) {
    current_ioc = current_ioc_raw ?? {}
    ioc_value_raw = current_ioc["value"] ?? null
    ioc_type = current_ioc["type"] ?? "unknown"

    # Initialize result for this IOC
    ioc_result = {
        "ioc_value": ioc_value_raw,
        "ioc_type": ioc_type,
        "vt_analysis": null,
        "error": null
    }

    # Process IOC if value exists
    if (ioc_value_raw != null) {
        # Convert to string for type safety
        ioc_value = str(ioc_value_raw)

        # Call appropriate VirusTotal tool based on IOC type
        if (ioc_type == "ip") {
        # IP reputation analysis
        vt_report = app::virustotal::ip_reputation(ip=ioc_value)

        # Parse metrics with null-coalescing defaults
        reputation_summary = vt_report["reputation_summary"] ?? {}
        malicious = reputation_summary["malicious"] ?? 0
        suspicious = reputation_summary["suspicious"] ?? 0
        harmless = reputation_summary["harmless"] ?? 0
        undetected = reputation_summary["undetected"] ?? 0
        total_engines = malicious + suspicious + harmless + undetected

        # Calculate risk (protect against division by zero)
        risk_score = 0
        if (total_engines > 0) {
            risk_score = (malicious / total_engines) * 100
        }

        # Determine threat level
        threat_level = "Low"
        if (malicious >= 5) {
            threat_level = "High"
            high_risk_count = high_risk_count + 1
        } elif (malicious >= 2 or suspicious >= 3) {
            threat_level = "Medium"
            medium_risk_count = medium_risk_count + 1
        } else {
            low_risk_count = low_risk_count + 1
        }

        ioc_result["vt_analysis"] = {
            "detection_type": "ip_reputation",
            "threat_level": threat_level,
            "risk_score": risk_score,
            "detections": {
                "malicious": malicious,
                "suspicious": suspicious,
                "harmless": harmless,
                "total_engines": total_engines
            }
        }
        total_analyzed = total_analyzed + 1

    } elif (ioc_type == "domain") {
        # Domain reputation analysis
        vt_report = app::virustotal::domain_reputation(domain=ioc_value)

        # Parse metrics with null-coalescing defaults
        reputation_summary = vt_report["reputation_summary"] ?? {}
        malicious = reputation_summary["malicious"] ?? 0
        suspicious = reputation_summary["suspicious"] ?? 0
        harmless = reputation_summary["harmless"] ?? 0
        undetected = reputation_summary["undetected"] ?? 0
        total_engines = malicious + suspicious + harmless + undetected

        # Calculate risk (protect against division by zero)
        risk_score = 0
        if (total_engines > 0) {
            risk_score = (malicious / total_engines) * 100
        }

        # Determine threat level
        threat_level = "Low"
        if (malicious >= 5) {
            threat_level = "High"
            high_risk_count = high_risk_count + 1
        } elif (malicious >= 2 or suspicious >= 3) {
            threat_level = "Medium"
            medium_risk_count = medium_risk_count + 1
        } else {
            low_risk_count = low_risk_count + 1
        }

        ioc_result["vt_analysis"] = {
            "detection_type": "domain_reputation",
            "threat_level": threat_level,
            "risk_score": risk_score,
            "detections": {
                "malicious": malicious,
                "suspicious": suspicious,
                "harmless": harmless,
                "total_engines": total_engines
            }
        }
        total_analyzed = total_analyzed + 1

    } elif (ioc_type == "url") {
        # URL reputation analysis
        vt_report = app::virustotal::url_reputation(url=ioc_value)

        # Parse metrics with null-coalescing defaults
        reputation_summary = vt_report["reputation_summary"] ?? {}
        malicious = reputation_summary["malicious"] ?? 0
        suspicious = reputation_summary["suspicious"] ?? 0
        harmless = reputation_summary["harmless"] ?? 0
        undetected = reputation_summary["undetected"] ?? 0
        total_engines = malicious + suspicious + harmless + undetected

        # Calculate risk (protect against division by zero)
        risk_score = 0
        if (total_engines > 0) {
            risk_score = (malicious / total_engines) * 100
        }

        # Determine threat level
        threat_level = "Low"
        if (malicious >= 5) {
            threat_level = "High"
            high_risk_count = high_risk_count + 1
        } elif (malicious >= 2 or suspicious >= 3) {
            threat_level = "Medium"
            medium_risk_count = medium_risk_count + 1
        } else {
            low_risk_count = low_risk_count + 1
        }

        ioc_result["vt_analysis"] = {
            "detection_type": "url_reputation",
            "threat_level": threat_level,
            "risk_score": risk_score,
            "detections": {
                "malicious": malicious,
                "suspicious": suspicious,
                "harmless": harmless,
                "total_engines": total_engines
            }
        }
        total_analyzed = total_analyzed + 1

    } elif (ioc_type == "filehash") {
        # File hash reputation analysis
        vt_report = app::virustotal::file_reputation(file_hash=ioc_value)

        # Parse metrics with null-coalescing defaults
        reputation_summary = vt_report["reputation_summary"] ?? {}
        malicious = reputation_summary["malicious"] ?? 0
        suspicious = reputation_summary["suspicious"] ?? 0
        harmless = reputation_summary["harmless"] ?? 0
        undetected = reputation_summary["undetected"] ?? 0
        total_engines = malicious + suspicious + harmless + undetected

        # Calculate risk (protect against division by zero)
        risk_score = 0
        if (total_engines > 0) {
            risk_score = (malicious / total_engines) * 100
        }

        # Determine threat level
        threat_level = "Low"
        if (malicious >= 5) {
            threat_level = "High"
            high_risk_count = high_risk_count + 1
        } elif (malicious >= 2 or suspicious >= 3) {
            threat_level = "Medium"
            medium_risk_count = medium_risk_count + 1
        } else {
            low_risk_count = low_risk_count + 1
        }

        ioc_result["vt_analysis"] = {
            "detection_type": "file_reputation",
            "threat_level": threat_level,
            "risk_score": risk_score,
            "detections": {
                "malicious": malicious,
                "suspicious": suspicious,
                "harmless": harmless,
                "total_engines": total_engines
            }
        }
        total_analyzed = total_analyzed + 1

        } else {
            # Unsupported IOC type
            ioc_result["error"] = "IOC type '${ioc_type}' not supported for VirusTotal batch analysis"
            error_count = error_count + 1
        }
    } else {
        # IOC value is null
        ioc_result["error"] = "IOC value is null"
        error_count = error_count + 1
    }

    # Add to batch results
    batch_results = batch_results + [ioc_result]
}

# Generate LLM-powered executive summary with null-safe field extraction
alert_title = alert["title"] ?? "unknown alert"
alert_severity = alert["severity"] ?? "unknown"
source_product = alert["source_product"] ?? "unknown"
source_vendor = alert["source_vendor"] ?? "unknown"
event_time = alert["triggering_event_time"] ?? "unknown"

summary_prompt = """Analyze this batch VirusTotal IOC assessment for security decision-making:

**Alert Context:**
- Alert Title: ${alert_title}
- Alert Severity: ${alert_severity}
- Source: ${source_product} (${source_vendor})
- Detection Time: ${event_time}

**Batch Analysis Results:**
- Total IOCs Analyzed: ${total_analyzed}
- High Risk IOCs: ${high_risk_count}
- Medium Risk IOCs: ${medium_risk_count}
- Low Risk IOCs: ${low_risk_count}
- Analysis Errors: ${error_count}

**IOC Details:**
${to_json(batch_results)}

Provide a concise executive summary with:
1. Overall threat assessment (1-2 sentences)
2. Key findings about high/medium risk IOCs
3. Recommended immediate actions
4. Suggested investigation priorities

Format as a professional security advisory."""

# Get AI-powered summary
executive_summary = llm_run(summary_prompt)

# Determine overall risk level for the batch
overall_risk_level = "Low"
if (high_risk_count >= 1) {
    overall_risk_level = "High"
} elif (medium_risk_count >= 2) {
    overall_risk_level = "Medium"
}

# Determine recommended action
recommended_action = "MONITOR"
if (overall_risk_level == "High") {
    recommended_action = "INVESTIGATE_IMMEDIATELY"
} elif (overall_risk_level == "Medium") {
    recommended_action = "INVESTIGATE_AND_MONITOR"
}

# Create enrichment data structure
enrichment_data = {
    "data_source": "VirusTotal",
    "analysis_type": "batch_ioc_reputation",
    "summary": {
        "total_iocs": len(iocs),
        "analyzed": total_analyzed,
        "high_risk": high_risk_count,
        "medium_risk": medium_risk_count,
        "low_risk": low_risk_count,
        "errors": error_count,
        "overall_risk_level": overall_risk_level
    },
    "ioc_results": batch_results,
    "recommended_action": recommended_action,
    "ai_analysis": executive_summary
}

# Add enrichment to alert using standardized function
return enrich_alert(alert, enrichment_data)
