# MaxMind GeoIP2 Integration

IP geolocation integration using MaxMind's GeoIP2 Precision Web Services API.

## Overview

MaxMind provides accurate geolocation data for IPv4 and IPv6 addresses, including:
- City, state, country, and continent
- Latitude/longitude coordinates
- Time zone information
- Postal codes
- AS number and organization
- Domain information

## Authentication

Requires MaxMind account credentials:

- **account_id**: Your MaxMind account ID
- **license_key**: Your MaxMind license key (generate from account dashboard)

## Actions

### health_check
Tests connectivity to MaxMind GeoIP2 API.

### geolocate_ip
Get geolocation information for an IP address.

**Parameters:**
- `ip` (required): IPv4 or IPv6 address to geolocate

**Returns:**
- City, state, country, continent names
- Geographic coordinates (latitude/longitude)
- Time zone
- Postal code
- AS number and organization
- Domain information

## Archetype Mappings

**Geolocation:**
- `lookup_ip` → `geolocate_ip`

## API Limits

MaxMind GeoIP2 Precision Web Services has rate limits and usage-based pricing. Consult your MaxMind account for details.

## Migration Notes

## References

- [MaxMind GeoIP2 Precision Web Services](https://dev.maxmind.com/geoip/geoip2/web-services)
- [GeoIP2 City API Documentation](https://dev.maxmind.com/geoip/docs/web-services?lang=en)
