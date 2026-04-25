"""Integration tests for Global DNS integration.

These tests make real DNS queries against public domains.
Marked with @pytest.mark.integration.
"""

import pytest

from analysi.integrations.framework.integrations.global_dns.actions import (
    GetMxRecordsAction,
    GetNsRecordsAction,
    GetSoaRecordAction,
    GetTxtRecordsAction,
    HealthCheckAction,
    ResolveDomainAction,
    ReverseLookupAction,
)


@pytest.fixture
def action_instance():
    """Create action instance with Google DNS server."""
    return lambda action_class: action_class(
        integration_id="global-dns",
        action_id="test_action",
        settings={"dns_server": "8.8.8.8", "timeout": 10},
        credentials={},
    )


# ============================================================================
# Health Check Integration Test
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_check_real_dns(action_instance):
    """Test health check against real DNS."""
    action = action_instance(HealthCheckAction)

    result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "resolved_ips" in result["data"]
    assert len(result["data"]["resolved_ips"]) > 0


# ============================================================================
# Resolve Domain Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_domain_google_a_record(action_instance):
    """Test resolving google.com A record."""
    action = action_instance(ResolveDomainAction)

    result = await action.execute(domain="google.com")

    assert result["status"] == "success"
    assert result["domain"] == "google.com"
    assert result["record_type"] == "A"
    assert len(result["records"]) > 0
    # Verify IP format
    assert all("." in ip for ip in result["records"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_domain_cloudflare_aaaa_record(action_instance):
    """Test resolving cloudflare.com AAAA record (IPv6)."""
    action = action_instance(ResolveDomainAction)

    result = await action.execute(domain="cloudflare.com", record_type="AAAA")

    assert result["status"] == "success"
    assert result["record_type"] == "AAAA"
    assert len(result["records"]) > 0
    # Verify IPv6 format (contains colons)
    assert all(":" in ip for ip in result["records"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_domain_nonexistent(action_instance):
    """Test resolving non-existent domain."""
    action = action_instance(ResolveDomainAction)

    result = await action.execute(domain="this-domain-does-not-exist-12345.invalid")

    # NXDOMAIN is a successful lookup that found nothing (not_found=True),
    # not an error — the DNS infrastructure worked correctly.
    assert result["status"] == "success"
    assert result["not_found"] is True


# ============================================================================
# Reverse Lookup Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reverse_lookup_google_dns(action_instance):
    """Test reverse DNS lookup for Google DNS (8.8.8.8)."""
    action = action_instance(ReverseLookupAction)

    result = await action.execute(ip="8.8.8.8")

    assert result["status"] == "success"
    assert result["ip"] == "8.8.8.8"
    assert len(result["domains"]) > 0
    assert "google" in result["primary_domain"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reverse_lookup_cloudflare_dns(action_instance):
    """Test reverse DNS lookup for Cloudflare DNS (1.1.1.1)."""
    action = action_instance(ReverseLookupAction)

    result = await action.execute(ip="1.1.1.1")

    assert result["status"] == "success"
    assert result["ip"] == "1.1.1.1"
    assert len(result["domains"]) > 0
    # Cloudflare's 1.1.1.1 resolves to "one.one.one.one" (their branding)
    assert "one.one" in result["primary_domain"].lower()


# ============================================================================
# MX Records Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_mx_records_gmail(action_instance):
    """Test getting MX records for gmail.com."""
    action = action_instance(GetMxRecordsAction)

    result = await action.execute(domain="gmail.com")

    assert result["status"] == "success"
    assert result["domain"] == "gmail.com"
    assert len(result["mx_records"]) > 0
    # Gmail MX records should contain google.com
    assert any("google.com" in mx["exchange"] for mx in result["mx_records"])
    # Check priority field exists
    assert all("priority" in mx for mx in result["mx_records"])
    # Check sorted by priority
    priorities = [mx["priority"] for mx in result["mx_records"]]
    assert priorities == sorted(priorities)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_mx_records_no_mx(action_instance):
    """Test domain with no MX records."""
    action = action_instance(GetMxRecordsAction)

    # Use a domain that likely has no MX records (like a pure CDN domain)
    result = await action.execute(domain="cloudflare.net")

    # Should either succeed with empty list or return NoAnswer
    if result["status"] == "success":
        # Some domains might have MX records
        assert "mx_records" in result
    else:
        assert result["error_type"] in ["NoAnswer", "NXDOMAIN"]


# ============================================================================
# TXT Records Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_txt_records_google(action_instance):
    """Test getting TXT records for google.com (SPF, etc.)."""
    action = action_instance(GetTxtRecordsAction)

    result = await action.execute(domain="google.com")

    assert result["status"] == "success"
    assert result["domain"] == "google.com"
    assert len(result["txt_records"]) > 0
    # Google should have SPF record
    assert any("v=spf1" in txt for txt in result["txt_records"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_txt_records_verification(action_instance):
    """Test TXT records often contain verification strings."""
    action = action_instance(GetTxtRecordsAction)

    result = await action.execute(domain="github.com")

    assert result["status"] == "success"
    assert len(result["txt_records"]) > 0
    # TXT records should be strings
    assert all(isinstance(txt, str) for txt in result["txt_records"])


# ============================================================================
# NS Records Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_ns_records_cloudflare(action_instance):
    """Test getting NS records for cloudflare.com."""
    action = action_instance(GetNsRecordsAction)

    result = await action.execute(domain="cloudflare.com")

    assert result["status"] == "success"
    assert result["domain"] == "cloudflare.com"
    assert len(result["nameservers"]) > 0
    # Cloudflare should have nameservers with cloudflare in the name
    assert any("cloudflare" in ns.lower() for ns in result["nameservers"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_ns_records_google(action_instance):
    """Test getting NS records for google.com."""
    action = action_instance(GetNsRecordsAction)

    result = await action.execute(domain="google.com")

    assert result["status"] == "success"
    assert len(result["nameservers"]) > 0
    # Google should have multiple nameservers
    assert len(result["nameservers"]) >= 2


# ============================================================================
# SOA Record Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_soa_record_example(action_instance):
    """Test getting SOA record for example.com."""
    action = action_instance(GetSoaRecordAction)

    result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["domain"] == "example.com"
    assert "soa_record" in result

    soa = result["soa_record"]
    # Verify all SOA fields are present
    assert "mname" in soa  # Primary nameserver
    assert "rname" in soa  # Responsible email
    assert "serial" in soa  # Serial number
    assert "refresh" in soa
    assert "retry" in soa
    assert "expire" in soa
    assert "minimum" in soa

    # Serial should be a reasonable number
    assert isinstance(soa["serial"], int)
    assert soa["serial"] > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_soa_record_google(action_instance):
    """Test getting SOA record for google.com."""
    action = action_instance(GetSoaRecordAction)

    result = await action.execute(domain="google.com")

    assert result["status"] == "success"
    soa = result["soa_record"]
    # Google's nameservers should be in the mname
    assert "ns" in soa["mname"].lower()


# ============================================================================
# Multi-Server Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_with_cloudflare_dns():
    """Test resolution using Cloudflare DNS setting (system resolver is used)."""
    action = ResolveDomainAction(
        integration_id="global-dns",
        action_id="test_action",
        settings={"dns_server": "1.1.1.1", "timeout": 10},
        credentials={},
    )

    result = await action.execute(domain="cloudflare.com")

    assert result["status"] == "success"
    # dns_server reports the actual system resolver, not the configured one
    # (see _make_resolver: system resolver is always used, setting is informational)
    assert result["dns_server"]  # non-empty string
    assert len(result["records"]) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_with_quad9_dns():
    """Test resolution using Quad9 DNS setting (system resolver is used)."""
    action = ResolveDomainAction(
        integration_id="global-dns",
        action_id="test_action",
        settings={"dns_server": "9.9.9.9", "timeout": 10},
        credentials={},
    )

    result = await action.execute(domain="quad9.net")

    assert result["status"] == "success"
    # dns_server reports the actual system resolver, not the configured one
    assert result["dns_server"]  # non-empty string
    assert len(result["records"]) > 0
