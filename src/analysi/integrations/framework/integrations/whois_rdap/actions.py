"""WHOIS RDAP integration actions.

This module provides IP WHOIS lookups via the RDAP protocol using the ipwhois
library. The ipwhois library is synchronous; all operations are wrapped with
asyncio.to_thread() to avoid blocking the event loop.

No authentication is required — RDAP is a free public protocol.
"""

import asyncio
import ipaddress
from typing import Any

from ipwhois import IPDefinedError, IPWhois

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.whois_rdap.constants import (
    ERROR_QUERY,
    ERROR_TYPE_IP_DEFINED,
    ERROR_TYPE_QUERY,
    ERROR_TYPE_VALIDATION,
    HEALTH_CHECK_IP,
    JSON_ASN,
    JSON_ASN_REGISTRY,
    JSON_COUNTRY_CODE,
    JSON_NETS,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

def _is_valid_ip(ip: str) -> bool:
    """Return True if ip is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def _lookup_rdap(ip: str) -> dict[str, Any]:
    """Perform a synchronous RDAP lookup for the given IP address.

    This function is meant to be called via asyncio.to_thread().

    Raises:
        IPDefinedError: If the IP is within a special-use range.
        Exception: On any other lookup failure.
    """
    obj_whois = IPWhois(ip)
    return obj_whois.lookup_rdap(inc_nir=False)

def _build_summary(whois_response: dict[str, Any]) -> dict[str, Any]:
    """Build a summary dict from an RDAP response (mirrors the upstream summary logic)."""
    summary: dict[str, Any] = {}

    if "asn_registry" in whois_response:
        summary[JSON_ASN_REGISTRY] = whois_response["asn_registry"]

    if "asn" in whois_response:
        summary[JSON_ASN] = whois_response["asn"]

    if "asn_country_code" in whois_response:
        summary[JSON_COUNTRY_CODE] = whois_response["asn_country_code"]

    if "network" in whois_response:
        nets = whois_response["network"]
        wanted_keys = ["start_address", "end_address"]
        summary[JSON_NETS] = [{k: nets[k] for k in wanted_keys if k in nets}]

    return summary

class HealthCheckAction(IntegrationAction):
    """Test RDAP connectivity by querying a known public IP (8.8.8.8)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Verify that RDAP lookups are functional.

        Returns:
            Result with status=success and basic RDAP data for 8.8.8.8, or error.
        """
        ip = HEALTH_CHECK_IP
        logger.info("whois_rdap_health_check_start", ip=ip)

        try:
            whois_response = await asyncio.to_thread(_lookup_rdap, ip)

            # Basic identity check: the response should echo back the queried IP
            if whois_response.get("query") != ip:
                logger.error("whois_rdap_health_check_identity_mismatch", ip=ip)
                return {
                    "healthy": False,
                    "status": STATUS_ERROR,
                    "error": "RDAP response query field does not match requested IP",
                    "error_type": "IdentityMismatch",
                }

            logger.info("whois_rdap_health_check_success", ip=ip)
            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "RDAP connectivity test passed",
                "data": {
                    "healthy": True,
                    "test_ip": ip,
                    "asn": whois_response.get("asn"),
                    "asn_registry": whois_response.get("asn_registry"),
                },
            }

        except IPDefinedError as e:
            # Should not happen for 8.8.8.8 — indicates a deeper problem
            logger.error(
                "whois_rdap_health_check_ip_defined_error", ip=ip, error=str(e)
            )
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_IP_DEFINED,
                "data": {"healthy": False},
            }
        except Exception as e:
            logger.error("whois_rdap_health_check_failed", ip=ip, error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": ERROR_QUERY.format(e),
                "error_type": ERROR_TYPE_QUERY,
                "data": {"healthy": False},
            }

class WhoisIpAction(IntegrationAction):
    """Execute a WHOIS/RDAP lookup on an IPv4 or IPv6 address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up registration data for an IP address using RDAP.

        Args:
            **kwargs: Must contain 'ip' — the IPv4 or IPv6 address to query.

        Returns:
            Result with full RDAP response and a summary of key fields, or error.
        """
        ip = kwargs.get("ip")
        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter: ip",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not _is_valid_ip(ip):
            return {
                "status": STATUS_ERROR,
                "error": f"Invalid IP address: {ip}",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        logger.info("whois_rdap_whois_ip_start", ip=ip)

        try:
            whois_response = await asyncio.to_thread(_lookup_rdap, ip)

            # convert objects dict to a list so keys
            # (which change per response) are not needed — handles are stored
            # inside each object as object[key].handle
            if whois_response.get("objects"):
                objects = whois_response["objects"]
                whois_response["objects"] = [objects[key] for key in objects]

            summary = _build_summary(whois_response)

            logger.info("whois_rdap_whois_ip_success", ip=ip)
            return {
                "status": STATUS_SUCCESS,
                "ip": ip,
                "data": whois_response,
                "summary": summary,
            }

        except IPDefinedError as e:
            # IP is within a special-use/reserved range — not an error per se.
            # upstream treats this as APP_SUCCESS with a message. We return success
            # with not_found=True so Cy scripts don't crash on reserved IPs.
            logger.info("whois_rdap_whois_ip_reserved", ip=ip, reason=str(e))
            return {
                "status": STATUS_SUCCESS,
                "ip": ip,
                "not_found": True,
                "message": str(e),
                "data": None,
                "summary": {},
            }
        except Exception as e:
            logger.error("whois_rdap_whois_ip_failed", ip=ip, error=str(e))
            return {
                "status": STATUS_ERROR,
                "ip": ip,
                "error": ERROR_QUERY.format(e),
                "error_type": ERROR_TYPE_QUERY,
            }
