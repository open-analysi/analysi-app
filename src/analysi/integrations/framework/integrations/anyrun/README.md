# ANY.RUN Sandbox Integration

Interactive malware analysis sandbox for detonating files and URLs with real-time behavioral analysis.

## Features

- **Health Check**: Verify API key and connectivity
- **Detonate URL**: Submit URLs for sandbox analysis (Windows, Linux, Android VMs)
- **Detonate File**: Submit files (base64-encoded) for sandbox analysis
- **Get Report**: Retrieve detailed analysis reports with verdict, tags, and IOC data

## Configuration

### Credentials

| Field | Required | Description |
|-------|----------|-------------|
| `api_key` | Yes | ANY.RUN API key (from https://app.any.run/profile) |

### Settings

| Field | Default | Description |
|-------|---------|-------------|
| `base_url` | `https://api.any.run/v1` | API base URL |
| `timeout` | `300` | HTTP request timeout (seconds) |

## Actions

### health_check

No parameters. Verifies the API key is valid and the API is reachable.

### detonate_url

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | URL to detonate (5-512 chars) |
| `os_type` | No | `windows` | `windows`, `linux`, or `android` |
| `env_type` | No | `complete` | `clean`, `office`, `complete`, `development` |
| `env_bitness` | No | `64` | 32 or 64 |
| `env_version` | No | `10` | OS version (e.g., "7", "10", "11") |
| `browser` | No | `Microsoft Edge` | Browser for URL analysis |
| `opt_privacy_type` | No | `bylink` | `public`, `bylink`, `owner`, `byteam` |
| `opt_timeout` | No | `120` | Analysis timeout in sandbox (seconds) |

Returns `analysis_id` and `analysis_url` for tracking.

### detonate_file

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `file_content` | Yes | - | Base64-encoded file bytes |
| `filename` | Yes | - | Original filename with extension |
| `os_type` | No | `windows` | `windows`, `linux`, or `android` |
| `env_type` | No | `complete` | `clean`, `office`, `complete` |
| `opt_privacy_type` | No | `bylink` | Privacy setting |
| `opt_timeout` | No | `120` | Analysis timeout (seconds) |

Returns `analysis_id`, `filename`, and `analysis_url`.

### get_report

| Parameter | Required | Description |
|-----------|----------|-------------|
| `analysis_id` | Yes | ANY.RUN analysis UUID |

Returns `verdict`, `tags`, `object_type`, `object_value`, and full `report` data. Returns `not_found=True` for unknown analysis IDs (does not crash Cy scripts).

## Archetype Mappings

**Sandbox** archetype:
- `submit_url` -> `detonate_url`
- `submit_file` -> `detonate_file`
- `get_analysis_report` -> `get_report`

## Migration Notes

### Key differences from upstream version

1. **REST API instead of SDK**: upstream used the proprietary `anyrun` Python SDK (`SandboxConnector`, `LookupConnector`). Naxos calls the REST API directly via `self.http_request()`.

2. **Simplified OS selection**: upstream had separate actions per OS (`detonate_url_windows`, `detonate_url_linux`, `detonate_url_android`). Naxos uses a single `detonate_url` action with an `os_type` parameter.

3. **File input**: Naxos accepts base64-encoded file content directly.

4. **Actions not migrated**: The following prior actions were out of scope for this migration:
   - `get_reputation` (TI Lookup -- uses separate LookupConnector API)
   - `search_analysis_history` (history search)
   - `get_ioc` (IOC extraction from analysis)
   - `get_report_stix`, `get_report_html`, `get_report_misp` (alternative report formats)
   - `download_pcap` (PCAP download)
   - `delete_analysis` (task deletion)
   - `get_analysis_verdict` (standalone verdict retrieval)
   - `get_intelligence` (TI query)

## References

- [ANY.RUN API Documentation](https://any.run/api-documentation/)
- [ANY.RUN Sandbox](https://app.any.run/)
