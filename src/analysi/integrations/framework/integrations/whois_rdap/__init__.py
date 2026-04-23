"""WHOIS RDAP integration for IP address registration data lookup.

This integration provides WHOIS lookups via the RDAP protocol using the ipwhois
library. It requires no authentication — RDAP is a free public protocol.
"""

__all__ = ["INTEGRATION_ID"]

INTEGRATION_ID = "whois_rdap"
