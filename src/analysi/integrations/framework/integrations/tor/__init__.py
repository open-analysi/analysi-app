"""Tor integration for checking Tor exit nodes.

This integration checks if IP addresses are Tor exit nodes by querying
the Tor Project's public exit node lists. No authentication required.
"""

__all__ = ["INTEGRATION_ID"]

INTEGRATION_ID = "tor"
