"""MaxMind GeoIP2 integration for Naxos framework.

This integration provides IP geolocation using MaxMind's GeoIP2 Precision Web Services API.
"""

from .actions import GeolocateIpAction, HealthCheckAction

__all__ = [
    "GeolocateIpAction",
    "HealthCheckAction",
]
