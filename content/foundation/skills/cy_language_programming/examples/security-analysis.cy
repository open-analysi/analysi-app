# Security IP Analysis Example
# Demonstrates: Complex workflow, conditional logic, multiple integrations, risk scoring

# Get input data
ip_address = input.ip_address
alert_context = input.context

log("Starting security analysis for ${ip_address}")

# Initialize risk tracking
ip_risk_scores = {}
ip_risk_scores[ip_address] = 0

# Gather threat intelligence from multiple sources (parallel)
# These API calls run concurrently for maximum performance
vt_data = app::virustotal::ip_reputation(ip_address=ip_address)
shodan_data = app::shodan::host_lookup(ip=ip_address)
geo_data = app::geoip::lookup(ip=ip_address)

log("Threat intelligence gathered from 3 sources")

# Calculate reputation risk score
malicious_count = vt_data.malicious_score
total_engines = vt_data.total_engines
detection_ratio = 0

if (total_engines > 0) {
    detection_ratio = malicious_count / total_engines
}

reputation_score = detection_ratio * 100

# Calculate infrastructure risk score
open_ports = len(shodan_data.ports)
vulnerable_services = shodan_data.vulnerabilities
infrastructure_score = (open_ports * 2) + (vulnerable_services * 10)

# Calculate geographic risk score
high_risk_countries = ["XX", "YY", "ZZ"]  # Example country codes
country_code = geo_data.country_code
geo_risk = 0

for (risky_country in high_risk_countries) {
    if (country_code == risky_country) {
        geo_risk = 25
    }
}

# Calculate composite risk score
total_risk = reputation_score + infrastructure_score + geo_risk
ip_risk_scores[ip_address] = total_risk

# Determine threat level based on risk score
threat_level = "Low"
recommended_action = "MONITOR"

if (total_risk >= 80) {
    threat_level = "Critical"
    recommended_action = "BLOCK_IMMEDIATELY"
} elif (total_risk >= 50) {
    threat_level = "High"
    recommended_action = "INVESTIGATE"
} elif (total_risk >= 25) {
    threat_level = "Medium"
    recommended_action = "MONITOR_CLOSELY"
}

log("Risk assessment complete: ${threat_level} (score: ${total_risk})")

# Build comprehensive security report
report = {
    "ip_address": ip_address,
    "alert_context": alert_context,
    "threat_assessment": {
        "level": threat_level,
        "total_risk_score": total_risk,
        "recommended_action": recommended_action,
        "component_scores": {
            "reputation": reputation_score,
            "infrastructure": infrastructure_score,
            "geographic": geo_risk
        }
    },
    "intelligence": {
        "virustotal": {
            "malicious_count": malicious_count,
            "total_engines": total_engines,
            "detection_ratio": detection_ratio
        },
        "infrastructure": {
            "open_ports": open_ports,
            "vulnerable_services": vulnerable_services
        },
        "location": {
            "country": geo_data.country_name,
            "country_code": country_code,
            "is_high_risk_region": geo_risk > 0
        }
    }
}

return report
