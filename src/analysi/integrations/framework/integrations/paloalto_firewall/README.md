# Palo Alto Networks Firewall Integration

Enterprise firewall integration for URL/IP/application blocking and security policy management.

## Overview

This integration provides actions for managing Palo Alto Networks Firewall security policies including:
- URL blocking and unblocking
- IP address blocking and unblocking
- Application blocking and unblocking
- Application listing and discovery

## Authentication

The integration uses username/password authentication to obtain an API key from the firewall.

### Required Credentials
- **device**: Firewall IP address or hostname
- **username**: Administrator username
- **password**: Administrator password
- **verify_server_cert** (optional): Verify SSL certificate (default: true)

## Actions

### Health Check
Test connectivity to the firewall and validate credentials.

### Block URL
Block a URL by adding it to a custom URL category and creating/updating a security policy.

**Parameters:**
- `url` (required): URL to block
- `vsys` (optional): Virtual system, defaults to vsys1
- `sec_policy` (optional): Security policy to insert before

### Unblock URL
Remove a URL from the blocked URL category.

**Parameters:**
- `url` (required): URL to unblock
- `vsys` (optional): Virtual system, defaults to vsys1

### Block Application
Block an application by adding it to an application group and creating/updating a security policy.

**Parameters:**
- `application` (required): Application name to block
- `vsys` (optional): Virtual system, defaults to vsys1

### Unblock Application
Remove an application from the blocked application group.

**Parameters:**
- `application` (required): Application name to unblock
- `vsys` (optional): Virtual system, defaults to vsys1

### Block IP
Block an IP address by creating an address object and adding it to a security policy.

**Parameters:**
- `ip` (required): IP address to block (supports IP, CIDR, range, FQDN)
- `vsys` (optional): Virtual system, defaults to vsys1
- `is_source_address` (optional): Block as source address instead of destination

**Supported IP Formats:**
- Single IP: `192.168.1.100`
- CIDR: `192.168.1.0/24`
- Range: `192.168.1.1-192.168.1.254`
- FQDN: `malicious.example.com`

### Unblock IP
Remove an IP address from the blocked address group.

**Parameters:**
- `ip` (required): IP address to unblock
- `vsys` (optional): Virtual system, defaults to vsys1
- `is_source_address` (optional): Unblock from source address list

### List Applications
List all applications available on the firewall (both predefined and custom).

**Parameters:**
- `vsys` (optional): Virtual system, defaults to vsys1

## How It Works

### URL Blocking
1. Creates a custom URL category named "Analysi URL Category" if not exists
2. Adds the URL to this category
3. Creates a URL filtering profile named "Analysi URL List" if not exists
4. Adds the category to the profile
5. Creates a security policy named "Analysi URL Security Policy" if not exists
6. Positions the policy before the first "allow" policy
7. Commits the configuration

### IP Blocking
1. Creates an address object with the IP
2. Tags the address object for tracking
3. Adds the address to an address group ("Analysi Network List" or "Analysi Network List Source")
4. Creates a security policy with deny action
5. Positions the policy at the top
6. Commits the configuration

### Application Blocking
1. Creates an application group named "Analysi App List" if not exists
2. Adds the application to this group
3. Creates a security policy named "Analysi App Security Policy" if not exists
4. Positions the policy at the top
5. Commits the configuration

## Security Policies

All security policies created by this integration include:
- Description: "Created by Analysi, please don't edit"
- Source/Destination: any
- Service: application-default
- Category: any
- Source-user: any

## Configuration Commits

All blocking/unblocking actions automatically commit the configuration changes. The integration polls the commit job status to ensure successful completion.

## Version Compatibility

- Tested with PAN-OS 10.2.1
- Supports PAN-OS 9.x and later
- Automatically adjusts HIP profile configuration based on version

## Archetype Mapping

This integration supports the **NetworkSecurity** archetype with the following mappings:
- `block_url` → Block URL
- `unblock_url` → Unblock URL
- `block_ip` → Block IP
- `unblock_ip` → Unblock IP

## Migration Notes
- Converted from synchronous requests to async httpx
- Improved error handling and logging
- Added comprehensive type hints
- Structured constants for maintainability
- Added archetype support for NetworkSecurity

## Dependencies

- httpx: Async HTTP client
- xmltodict: XML parsing for PAN-OS API responses
- structlog: Structured logging
