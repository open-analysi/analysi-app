# Global DNS Integration

Free DNS resolution and reverse lookup using public DNS servers (Google DNS, Cloudflare, etc.). No authentication required.

## Overview

This integration provides DNS query capabilities using public DNS resolvers. All actions are free to use and require no credentials.

**Key Features:**
- No authentication required
- Supports multiple public DNS servers (Google, Cloudflare, Quad9, etc.)
- Async DNS resolution using dnspython
- All standard DNS record types (A, AAAA, CNAME, MX, TXT, NS, SOA, PTR)

## Authentication

No authentication required. This integration uses free public DNS servers.

### Settings

- **dns_server** (optional): Preferred DNS server IP address
  - Default: `8.8.8.8` (Google Public DNS)
  - Alternatives: `1.1.1.1` (Cloudflare), `9.9.9.9` (Quad9)
- **timeout** (optional): Query timeout in seconds
  - Default: `5`
  - Range: 1-30 seconds

## Actions

### Health Check
Test DNS resolution by querying a known domain (google.com).

**Parameters:** None

### Resolve Domain
Resolve domain name to IP addresses.

**Parameters:**
- `domain` (required): Domain name to resolve (e.g., example.com)
- `record_type` (optional): DNS record type - A, AAAA, or CNAME (default: A)

**Example Use Cases:**
- Investigate phishing domains
- Verify C2 infrastructure
- Check domain resolution

### Reverse DNS Lookup
Perform reverse DNS lookup (IP to domain name) using PTR records.

**Parameters:**
- `ip` (required): IPv4 or IPv6 address for reverse lookup

**Example Use Cases:**
- Identify server owners from IP addresses
- Verify PTR records for email servers
- Investigate suspicious IP addresses

### Get MX Records
Get mail server (MX) records for a domain.

**Parameters:**
- `domain` (required): Domain name to query

**Returns:** List of mail servers sorted by priority

**Example Use Cases:**
- Email authentication investigations
- Phishing domain analysis
- Verify legitimate email infrastructure

### Get TXT Records
Get TXT records for a domain (SPF, DKIM, DMARC, verification).

**Parameters:**
- `domain` (required): Domain name to query

**Example Use Cases:**
- Verify SPF/DKIM/DMARC email authentication
- Check domain verification records
- Investigate domain ownership

### Get NS Records
Get nameserver (NS) records for a domain.

**Parameters:**
- `domain` (required): Domain name to query

**Example Use Cases:**
- Identify authoritative nameservers
- Track DNS infrastructure changes
- Investigate domain hijacking

### Get SOA Record
Get Start of Authority (SOA) record for a domain.

**Parameters:**
- `domain` (required): Domain name to query

**Returns:** SOA record with primary nameserver, responsible email, serial number, refresh/retry/expire/minimum TTL

**Example Use Cases:**
- Get DNS zone metadata
- Track zone serial numbers for change detection
- Identify DNS zone administrators

## Public DNS Servers

Popular free DNS servers you can configure:

| Provider | IP Address | Notes |
|----------|-----------|-------|
| Google Public DNS | 8.8.8.8, 8.8.4.4 | Default, reliable, fast |
| Cloudflare DNS | 1.1.1.1, 1.0.0.1 | Privacy-focused, very fast |
| Quad9 | 9.9.9.9, 149.112.112.112 | Security-focused, blocks malicious domains |
| OpenDNS | 208.67.222.222, 208.67.220.220 | Family-safe filtering options |

## Archetype Mapping

This integration supports the **DNS** archetype with the following mappings:

| Archetype Method | Action |
|------------------|--------|
| `resolve_domain` | Resolve Domain |
| `reverse_lookup` | Reverse DNS Lookup |
| `get_mx_records` | Get MX Records |
| `get_txt_records` | Get TXT Records |
| `get_ns_records` | Get NS Records |
| `get_soa_record` | Get SOA Record |

## Use Cases

### Phishing Investigation
1. **Resolve Domain** - Get IP addresses of suspicious domains
2. **Get MX Records** - Verify mail server configuration
3. **Get TXT Records** - Check SPF/DKIM/DMARC authentication
4. **Reverse Lookup** - Identify hosting provider from IP

### C2 Infrastructure Analysis
1. **Resolve Domain** - Map C2 domain to IP addresses
2. **Get NS Records** - Identify nameserver infrastructure
3. **Get SOA Record** - Get DNS zone metadata
4. **Reverse Lookup** - Identify server ownership

### Email Authentication
1. **Get MX Records** - Verify mail server configuration
2. **Get TXT Records** - Check SPF records for authorized senders
3. **Get TXT Records** - Verify DKIM and DMARC policies

## Dependencies

- **dnspython** (2.8.0+): DNS toolkit with native async support
  - Provides `dns.asyncresolver` for async DNS queries
  - Supports all DNS record types
  - 128+ million downloads/month
  - Pure Python, no C dependencies

## Error Handling

The integration handles common DNS errors gracefully:

- **NXDOMAIN**: Domain does not exist
- **NoAnswer**: Domain exists but has no records of the requested type
- **Timeout**: DNS query timed out (check timeout settings)
- **DNSException**: General DNS protocol errors

All errors are returned with structured error types for easy handling in workflows.
