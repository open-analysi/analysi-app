"""Global DNS integration actions.

This module provides DNS resolution actions using dnspython's async resolver.
All actions use public DNS servers (Google DNS, Cloudflare, etc.) and require
no authentication.
"""

from typing import Any

import dns.asyncresolver
import dns.exception
import dns.rdatatype
import dns.reversename

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

# Constants
DEFAULT_TIMEOUT = 5

def _make_resolver(settings: dict) -> tuple[dns.asyncresolver.Resolver, str]:
    """Create a DNS resolver using the system resolver.

    Always uses the system resolver (/etc/resolv.conf) which in Docker
    points to 127.0.0.11 — Docker's internal DNS proxy that forwards
    queries to the host's DNS servers. Direct UDP/TCP to external DNS
    servers (e.g. 8.8.8.8) fails inside Docker Desktop because container
    traffic to external IPs on port 53 is blocked by the VM networking.

    The dns_server setting is recorded for informational purposes but
    does not override the system resolver.
    """
    resolver = dns.asyncresolver.Resolver()
    timeout = settings.get("timeout", DEFAULT_TIMEOUT)
    resolver.timeout = timeout
    resolver.lifetime = timeout
    dns_server = resolver.nameservers[0] if resolver.nameservers else "system"
    return resolver, dns_server

class HealthCheckAction(IntegrationAction):
    """Health check for DNS resolution capability."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test DNS resolution by querying google.com.

        Returns:
            Result with status=success if DNS resolution works
        """
        try:
            resolver, dns_server = _make_resolver(self.settings)

            # Test query to google.com
            answers = await resolver.resolve("google.com", "A")

            return {
                "healthy": True,
                "status": "success",
                "message": "DNS resolution is working",
                "data": {
                    "healthy": True,
                    "dns_server": dns_server,
                    "test_query": "google.com",
                    "resolved_ips": [str(rdata) for rdata in answers],
                },
            }

        except dns.exception.Timeout:
            logger.error("dns_health_check_timeout_for_server", dns_server=dns_server)
            return {
                "healthy": False,
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
                "data": {"healthy": False},
            }
        except dns.exception.DNSException as e:
            logger.error("dns_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }
        except Exception as e:
            logger.error("unexpected_error_in_dns_health_check", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class ResolveDomainAction(IntegrationAction):
    """Resolve domain name to IP addresses."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Resolve domain to IP addresses.

        Args:
            **kwargs: Must contain 'domain' (required), 'record_type' (optional, default 'A')

        Returns:
            Result with list of IP addresses or error
        """
        domain = kwargs.get("domain")
        if not domain:
            return {
                "status": "error",
                "error": "Missing required parameter: domain",
                "error_type": "ValidationError",
            }

        record_type = kwargs.get("record_type", "A").upper()
        if record_type not in ["A", "AAAA", "CNAME"]:
            return {
                "status": "error",
                "error": f"Unsupported record type: {record_type}. Supported: A, AAAA, CNAME",
                "error_type": "ValidationError",
            }

        try:
            resolver, dns_server = _make_resolver(self.settings)

            answers = await resolver.resolve(domain, record_type)

            return {
                "status": "success",
                "domain": domain,
                "record_type": record_type,
                "records": [str(rdata) for rdata in answers],
                "dns_server": dns_server,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "message": f"Domain not found: {domain}",
            }
        except dns.resolver.NoAnswer:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "records": [],
                "message": f"No {record_type} records found for {domain}",
            }
        except dns.exception.Timeout:
            return {
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
            }
        except dns.exception.DNSException as e:
            logger.error("dns_resolution_failed_for", domain=domain, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("unexpected_error_resolving", domain=domain, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class ReverseLookupAction(IntegrationAction):
    """Perform reverse DNS lookup (IP to domain)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Reverse DNS lookup using PTR records.

        Args:
            **kwargs: Must contain 'ip' (IPv4 or IPv6 address)

        Returns:
            Result with domain name or error
        """
        ip = kwargs.get("ip")
        if not ip:
            return {
                "status": "error",
                "error": "Missing required parameter: ip",
                "error_type": "ValidationError",
            }

        try:
            resolver, dns_server = _make_resolver(self.settings)

            # Convert IP to reverse DNS name (e.g., 8.8.8.8 -> 8.8.8.8.in-addr.arpa)
            reverse_name = dns.reversename.from_address(ip)

            answers = await resolver.resolve(reverse_name, "PTR")

            # PTR records return domain names
            domains = [str(rdata.target).rstrip(".") for rdata in answers]

            return {
                "status": "success",
                "ip": ip,
                "domains": domains,
                "primary_domain": domains[0] if domains else None,
                "dns_server": dns_server,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "status": "success",
                "not_found": True,
                "ip": ip,
                "message": f"No PTR record found for IP: {ip}",
            }
        except dns.resolver.NoAnswer:
            return {
                "status": "success",
                "not_found": True,
                "ip": ip,
                "domains": [],
                "message": f"No PTR records found for {ip}",
            }
        except dns.exception.Timeout:
            return {
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
            }
        except dns.exception.DNSException as e:
            logger.error("reverse_lookup_failed_for", ip=ip, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error("unexpected_error_in_reverse_lookup_for", ip=ip, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetMxRecordsAction(IntegrationAction):
    """Get mail server (MX) records for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get MX records for domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with list of MX records (sorted by priority) or error
        """
        domain = kwargs.get("domain")
        if not domain:
            return {
                "status": "error",
                "error": "Missing required parameter: domain",
                "error_type": "ValidationError",
            }

        try:
            resolver, dns_server = _make_resolver(self.settings)

            answers = await resolver.resolve(domain, "MX")

            # MX records have priority and exchange (mail server)
            mx_records = [
                {
                    "priority": rdata.preference,
                    "exchange": str(rdata.exchange).rstrip("."),
                }
                for rdata in answers
            ]

            # Sort by priority (lower is higher priority)
            mx_records.sort(key=lambda x: x["priority"])

            return {
                "status": "success",
                "domain": domain,
                "mx_records": mx_records,
                "count": len(mx_records),
                "dns_server": dns_server,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "message": f"Domain not found: {domain}",
            }
        except dns.resolver.NoAnswer:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "mx_records": [],
                "message": f"No MX records found for {domain}",
            }
        except dns.exception.Timeout:
            return {
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
            }
        except dns.exception.DNSException as e:
            logger.error("mx_record_lookup_failed_for", domain=domain, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "unexpected_error_getting_mx_records_for", domain=domain, error=str(e)
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetTxtRecordsAction(IntegrationAction):
    """Get TXT records for a domain (SPF, DKIM, DMARC, verification)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get TXT records for domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with list of TXT records or error
        """
        domain = kwargs.get("domain")
        if not domain:
            return {
                "status": "error",
                "error": "Missing required parameter: domain",
                "error_type": "ValidationError",
            }

        try:
            resolver, dns_server = _make_resolver(self.settings)

            answers = await resolver.resolve(domain, "TXT")

            # TXT records can contain multiple strings, join them
            txt_records = [
                "".join([s.decode("utf-8") for s in rdata.strings]) for rdata in answers
            ]

            return {
                "status": "success",
                "domain": domain,
                "txt_records": txt_records,
                "count": len(txt_records),
                "dns_server": dns_server,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "message": f"Domain not found: {domain}",
            }
        except dns.resolver.NoAnswer:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "txt_records": [],
                "message": f"No TXT records found for {domain}",
            }
        except dns.exception.Timeout:
            return {
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
            }
        except dns.exception.DNSException as e:
            logger.error("txt_record_lookup_failed_for", domain=domain, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "unexpected_error_getting_txt_records_for", domain=domain, error=str(e)
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetNsRecordsAction(IntegrationAction):
    """Get nameserver (NS) records for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get NS records for domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with list of nameservers or error
        """
        domain = kwargs.get("domain")
        if not domain:
            return {
                "status": "error",
                "error": "Missing required parameter: domain",
                "error_type": "ValidationError",
            }

        try:
            resolver, dns_server = _make_resolver(self.settings)

            answers = await resolver.resolve(domain, "NS")

            nameservers = [str(rdata.target).rstrip(".") for rdata in answers]

            return {
                "status": "success",
                "domain": domain,
                "nameservers": nameservers,
                "count": len(nameservers),
                "dns_server": dns_server,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "message": f"Domain not found: {domain}",
            }
        except dns.resolver.NoAnswer:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "nameservers": [],
                "message": f"No NS records found for {domain}",
            }
        except dns.exception.Timeout:
            return {
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
            }
        except dns.exception.DNSException as e:
            logger.error("ns_record_lookup_failed_for", domain=domain, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "unexpected_error_getting_ns_records_for", domain=domain, error=str(e)
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetSoaRecordAction(IntegrationAction):
    """Get Start of Authority (SOA) record for a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get SOA record for domain.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with SOA record details or error
        """
        domain = kwargs.get("domain")
        if not domain:
            return {
                "status": "error",
                "error": "Missing required parameter: domain",
                "error_type": "ValidationError",
            }

        try:
            resolver, dns_server = _make_resolver(self.settings)

            answers = await resolver.resolve(domain, "SOA")

            # SOA record contains multiple fields
            soa = answers[0]  # Only one SOA record per zone
            soa_record = {
                "mname": str(soa.mname).rstrip("."),  # Primary nameserver
                "rname": str(soa.rname).rstrip("."),  # Responsible email
                "serial": soa.serial,  # Zone serial number
                "refresh": soa.refresh,  # Refresh interval
                "retry": soa.retry,  # Retry interval
                "expire": soa.expire,  # Expire time
                "minimum": soa.minimum,  # Minimum TTL
            }

            return {
                "status": "success",
                "domain": domain,
                "soa_record": soa_record,
                "dns_server": dns_server,
            }

        except dns.resolver.NXDOMAIN:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "message": f"Domain not found: {domain}",
            }
        except dns.resolver.NoAnswer:
            return {
                "status": "success",
                "not_found": True,
                "domain": domain,
                "soa_record": None,
                "message": f"No SOA record found for {domain}",
            }
        except dns.exception.Timeout:
            return {
                "status": "error",
                "error": "DNS query timed out",
                "error_type": "TimeoutError",
            }
        except dns.exception.DNSException as e:
            logger.error("soa_record_lookup_failed_for", domain=domain, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "unexpected_error_getting_soa_record_for", domain=domain, error=str(e)
            )
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
