# DomainTools Integration

DomainTools integration for domain intelligence, WHOIS lookups, and threat research.

## Overview

This integration provides access to DomainTools API for domain and IP intelligence gathering, including WHOIS data, historical records, reverse lookups, and domain reputation scoring.

## Authentication

DomainTools uses HMAC-SHA1 signature authentication with:
- **Username**: DomainTools API username
- **API Key**: DomainTools API key

Authentication is performed via HMAC signature generated from username, timestamp, and endpoint path.

## Available Actions

### Domain Intelligence
- **domain_reputation**: Get risk score and reputation assessment for a domain
- **whois_domain**: Get current WHOIS information for a domain
- **whois_ip**: Get WHOIS information for an IP address
- **whois_history**: Get historical WHOIS records for a domain
- **hosting_history**: Get registrar, IP, and nameserver change history

### Reverse Lookups
- **reverse_lookup_domain**: Get IP addresses associated with a domain
- **reverse_lookup_ip**: Get domains hosted on an IP address
- **reverse_whois_email**: Find domains registered to an email address

### Monitoring
- **brand_monitor**: Monitor for newly registered domains matching brand terms

### System
- **health_check**: Verify API connectivity and credentials

## Configuration

### Credentials
```json
{
  "username": "your-domaintools-username",
  "api_key": "your-domaintools-api-key"
}
```

### Settings
```json
{
  "timeout": 30
}
```

## Usage Examples

### Check Domain Reputation
```python
result = await domain_reputation_action.execute(
    domain="example.com",
    use_risk_api=False
)
```

### WHOIS Lookup
```python
result = await whois_domain_action.execute(
    domain="google.com"
)
```

### Reverse IP Lookup
```python
result = await reverse_lookup_ip_action.execute(
    ip="8.8.8.8"
)
```

### Find Domains by Email
```python
result = await reverse_whois_email_action.execute(
    email="admin@example.com",
    count_only=False,
    include_history=True
)
```

## Migration Notes
- REST API calls converted from `requests` to `httpx.AsyncClient`
- HMAC authentication preserved from upstream implementation
- All action parameters and response formats maintained for compatibility
- Added proper async/await handling throughout
- Enhanced error handling with specific error types

## API Documentation

For more information, see [DomainTools API Documentation](https://www.domaintools.com/resources/api-documentation/)
