# NIST NVD Integration

Integration with NIST National Vulnerability Database (NVD) for CVE vulnerability lookups.

## Overview

The NIST NVD integration provides access to the National Vulnerability Database, allowing you to query detailed information about Common Vulnerabilities and Exposures (CVEs). This integration is useful for vulnerability research, security assessments, and enriching security alerts with CVE details.

## Features

- **CVE Lookup**: Query detailed CVE information including CVSS scores, descriptions, references, and more
- **CISA KEV Support**: Identifies CVEs listed in CISA's Known Exploited Vulnerabilities catalog
- **CVSS Metrics**: Supports both CVSS v3.1 and v2 scoring
- **No Authentication Required**: NIST NVD API is public and requires no API key

## Configuration

### Settings

- **api_version** (string): NIST NVD API version (default: "2.0")
- **timeout** (integer): HTTP request timeout in seconds (default: 30)

### Credentials

No credentials required. The NIST NVD API is publicly accessible.

## Actions

### health_check

Check connectivity to the NIST NVD API.

**Parameters:** None

**Returns:**
- `status`: "success" or "error"
- `message`: Status message
- `data.healthy`: Boolean indicating if API is accessible
- `data.api_version`: Configured API version
- `data.base_url`: API base URL

### cve_lookup

Look up CVE information from the NIST NVD database.

**Parameters:**
- `cve` (string, required): CVE ID to look up (e.g., "CVE-2021-44228")

**Returns:**
- `status`: "success" or "error"
- `cve_id`: CVE identifier
- `description`: CVE description
- `published_date`: When the CVE was published
- `last_modified_date`: When the CVE was last updated
- `cvss_metrics`: Object containing CVSS scoring information:
  - `base_score`: CVSS base score (0-10)
  - `base_severity`: Severity rating (LOW, MEDIUM, HIGH, CRITICAL)
  - `attack_vector`: Attack vector (NETWORK, ADJACENT, LOCAL, PHYSICAL)
  - `attack_complexity`: Attack complexity (LOW, HIGH)
  - `exploitability_score`: Exploitability metric
  - `impact_score`: Impact metric
- `references`: List of reference URLs
- `cisa_kev`: (if applicable) CISA Known Exploited Vulnerability information:
  - `vulnerability_name`: CISA vulnerability name
  - `required_action`: Required remediation action
  - `due_date`: CISA remediation due date (cisaActionDue)
  - `date_added`: Date added to KEV catalog (cisaExploitAdd)

## Archetype Mappings

This integration implements the **VulnerabilityManagement** archetype:

- `get_vulnerabilities` → `cve_lookup`

## Example Usage

```python
# Look up the Log4j vulnerability
result = await cve_lookup(cve="CVE-2021-44228")

# Check if it's in CISA's KEV catalog
if result["cisa_kev"]:
    print(f"CISA Required Action: {result['cisa_kev']['required_action']}")
    print(f"Due Date: {result['cisa_kev']['due_date']}")

# Check severity
cvss = result["cvss_metrics"]
print(f"CVSS Score: {cvss['base_score']} ({cvss['base_severity']})")
```

## Rate Limits

The NIST NVD API has rate limits. If you encounter rate limiting (HTTP 429), the integration will return an error. Consider implementing exponential backoff in your automation workflows.

## References

- [NIST NVD API Documentation](https://nvd.nist.gov/developers)
- [CVE Program](https://cve.mitre.org/)
- [CISA Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)

## Migration Notes
- Converted to async/await pattern using httpx
- Added CISA KEV catalog support
- Enhanced error handling with specific error types
- Improved CVSS metrics extraction (supports both v3.1 and v2)
