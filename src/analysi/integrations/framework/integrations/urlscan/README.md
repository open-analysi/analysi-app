# urlscan.io Integration

Naxos integration for urlscan.io - a service for scanning and analyzing websites for security threats.

## Overview

urlscan.io is a sandbox for scanning URLs and websites. It provides:
- URL scanning and detonation
- Screenshot capture
- Threat intelligence searching by domain/IP
- Scan report retrieval

**Archetype**: Sandbox

## Configuration

### Credentials

- `api_key` (optional): urlscan.io API key
  - Required for: URL scanning, hunt operations
  - Optional for: Public report retrieval, health checks

### Settings

- `timeout` (integer, default: 120): HTTP request timeout in seconds

## Actions

### 1. Health Check (`health_check`)
Test connectivity to urlscan.io API.

**Type**: Connector (health_monitoring)

**Returns**:
- `healthy` (boolean): API accessibility status

### 2. Get Report (`get_report`)
Retrieve analysis report for a previously submitted URL scan.

**Type**: Tool

**Parameters**:
- `id` (string, required): Report UUID (submission ID)

**Returns**:
- `report_id`: The submission UUID
- `data`: Complete scan report with task info, stats, and analysis details
- `processing`: True if scan is still in progress

**Notes**:
- Polls up to 10 times with 15-second intervals for scan completion
- Returns partial info if scan is still processing after max attempts

### 3. Hunt Domain (`hunt_domain`)
Search for URLs associated with a domain in urlscan.io database.

**Type**: Tool

**Parameters**:
- `domain` (string, required): Domain name to search

**Returns**:
- `domain`: Searched domain
- `results_count`: Number of results found
- `data`: Search results with scan information

**Requirements**: API key required

### 4. Hunt IP (`hunt_ip`)
Search for URLs associated with an IP address in urlscan.io database.

**Type**: Tool

**Parameters**:
- `ip` (string, required): IP address to search (IPv4 or IPv6)

**Returns**:
- `ip`: Searched IP address
- `results_count`: Number of results found
- `data`: Search results with scan information

**Requirements**: API key required

### 5. Detonate URL (`detonate_url`)
Submit a URL for analysis and scanning.

**Type**: Tool

**Parameters**:
- `url` (string, required): URL to scan
- `private` (boolean, optional, default: false): Make scan private
- `tags` (string, optional): Comma-separated tags (max 10)
- `custom_agent` (string, optional): Custom user agent string
- `get_result` (boolean, optional, default: true): Wait for and retrieve results

**Returns**:
- `url`: Submitted URL
- `uuid`: Submission UUID for future reference
- `data`: Full scan report (if `get_result=true`)
- `submission_info`: Submission metadata

**Requirements**: API key required

**Notes**:
- When `get_result=true`, polls for completion (like `get_report`)
- When `get_result=false`, returns immediately with UUID
- Tags are deduplicated and limited to 10

### 6. Get Screenshot (`get_screenshot`)
Retrieve screenshot for a completed scan.

**Type**: Tool

**Parameters**:
- `report_id` (string, required): Report UUID

**Returns**:
- `report_id`: The submission UUID
- `screenshot`: Base64-encoded screenshot image
- `content_type`: Image MIME type (usually image/png)
- `size`: Screenshot size in bytes

## Archetype Mappings

Maps to **Sandbox** archetype:
- `submit_url` → `detonate_url`
- `get_analysis_report` → `get_report`

## Example Usage

### Scanning a URL
```python
# Submit and wait for results
result = await detonate_url_action.execute(
    url="https://example.com",
    tags="investigation,phishing",
    private=True,
    get_result=True
)

# Quick submission without waiting
result = await detonate_url_action.execute(
    url="https://suspicious.com",
    get_result=False
)
# Returns UUID immediately for later retrieval
```

### Threat Intelligence Lookup
```python
# Search for domain activity
result = await hunt_domain_action.execute(
    domain="malicious.com"
)

# Search for IP activity
result = await hunt_ip_action.execute(
    ip="1.2.3.4"
)
```

### Retrieving Results
```python
# Get full scan report
result = await get_report_action.execute(
    id="abc-123-def-456"
)

# Get screenshot
result = await get_screenshot_action.execute(
    report_id="abc-123-def-456"
)
```

## Error Handling

All actions return standardized error responses:
- `ValidationError`: Missing or invalid parameters
- `ConfigurationError`: Missing API key when required
- `HTTPStatusError`: HTTP errors from urlscan.io API
- `TimeoutError`: Request timeout exceeded
- `RequestError`: General network/request errors

## Rate Limits

urlscan.io enforces rate limits based on account type:
- Free: Limited submissions per day
- Pro: Higher rate limits

Rate limit errors return HTTP 429 and are surfaced as `HTTPStatusError`.

## Migration Notes

**Changes from upstream**:
- Async implementation using httpx instead of synchronous requests
- Simplified polling logic with async/await
- Standardized error handling and response format
- Base64-encoded screenshots returned directly (no vault storage)
- Consistent parameter naming across actions

**Preserved from upstream**:
- Polling intervals (15 seconds) and max attempts (10)
- Tag limit (10 tags)
- API key optional behavior (public access for some operations)
- Protocol truncation for URL categorization
