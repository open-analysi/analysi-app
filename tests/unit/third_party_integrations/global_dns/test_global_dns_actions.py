"""Unit tests for Global DNS integration actions.

All tests use mocked dns.asyncresolver to avoid real DNS queries.
Tests should run in <0.1s per test.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import dns.exception
import dns.resolver
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
    """Create action instance with default settings."""
    return lambda action_class: action_class(
        integration_id="test-dns",
        action_id="test_action",
        settings={"dns_server": "8.8.8.8", "timeout": 5},
        credentials={},
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(action_instance):
    """Test successful health check."""
    action = action_instance(HealthCheckAction)

    # Mock successful DNS resolution
    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter(["142.250.185.14"])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "google.com" in result["data"]["test_query"]


@pytest.mark.asyncio
async def test_health_check_timeout(action_instance):
    """Test health check timeout error."""
    action = action_instance(HealthCheckAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.exception.Timeout())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert result["data"]["healthy"] is False


# ============================================================================
# ResolveDomainAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_domain_a_record_success(action_instance):
    """Test successful A record resolution."""
    action = action_instance(ResolveDomainAction)

    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter(["93.184.216.34"])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["domain"] == "example.com"
    assert result["record_type"] == "A"
    assert "93.184.216.34" in result["records"]


@pytest.mark.asyncio
async def test_resolve_domain_aaaa_record_success(action_instance):
    """Test successful AAAA record resolution."""
    action = action_instance(ResolveDomainAction)

    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter(["2606:2800:220:1:248:1893:25c8:1946"])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com", record_type="AAAA")

    assert result["status"] == "success"
    assert result["record_type"] == "AAAA"
    assert len(result["records"]) > 0


@pytest.mark.asyncio
async def test_resolve_domain_missing_parameter(action_instance):
    """Test error when domain parameter is missing."""
    action = action_instance(ResolveDomainAction)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "domain" in result["error"]


@pytest.mark.asyncio
async def test_resolve_domain_invalid_record_type(action_instance):
    """Test error for unsupported record type."""
    action = action_instance(ResolveDomainAction)

    result = await action.execute(domain="example.com", record_type="INVALID")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Unsupported record type" in result["error"]


@pytest.mark.asyncio
async def test_resolve_domain_nxdomain(action_instance):
    """NXDOMAIN is a successful not-found, not an error."""
    action = action_instance(ResolveDomainAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NXDOMAIN())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="nonexistent.invalid")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "nonexistent.invalid"
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_resolve_domain_no_answer(action_instance):
    """NoAnswer is a successful not-found with empty records."""
    action = action_instance(ResolveDomainAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NoAnswer())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com", record_type="AAAA")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "example.com"
    assert result["records"] == []


# ============================================================================
# ReverseLookupAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reverse_lookup_success(action_instance):
    """Test successful reverse DNS lookup."""
    action = action_instance(ReverseLookupAction)

    mock_rdata = MagicMock()
    mock_rdata.target = "dns.google."
    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter([mock_rdata])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(ip="8.8.8.8")

    assert result["status"] == "success"
    assert result["ip"] == "8.8.8.8"
    assert "dns.google" in result["domains"]
    assert result["primary_domain"] == "dns.google"


@pytest.mark.asyncio
async def test_reverse_lookup_missing_parameter(action_instance):
    """Test error when IP parameter is missing."""
    action = action_instance(ReverseLookupAction)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "ip" in result["error"]


@pytest.mark.asyncio
async def test_reverse_lookup_nxdomain(action_instance):
    """NXDOMAIN on reverse lookup is a successful not-found."""
    action = action_instance(ReverseLookupAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NXDOMAIN())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(ip="192.0.2.1")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["ip"] == "192.0.2.1"
    assert "No PTR record" in result["message"]


@pytest.mark.asyncio
async def test_reverse_lookup_no_answer(action_instance):
    """NoAnswer on reverse lookup is a successful not-found with empty domains."""
    action = action_instance(ReverseLookupAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NoAnswer())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(ip="192.0.2.1")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["ip"] == "192.0.2.1"
    assert result["domains"] == []


# ============================================================================
# GetMxRecordsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_mx_records_success(action_instance):
    """Test successful MX record retrieval."""
    action = action_instance(GetMxRecordsAction)

    # Mock MX records with priority
    mx1 = MagicMock()
    mx1.preference = 10
    mx1.exchange = "smtp1.google.com."

    mx2 = MagicMock()
    mx2.preference = 20
    mx2.exchange = "smtp2.google.com."

    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter([mx1, mx2])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="gmail.com")

    assert result["status"] == "success"
    assert result["domain"] == "gmail.com"
    assert len(result["mx_records"]) == 2
    # Check sorted by priority
    assert result["mx_records"][0]["priority"] == 10
    assert "smtp1.google.com" in result["mx_records"][0]["exchange"]


@pytest.mark.asyncio
async def test_get_mx_records_missing_parameter(action_instance):
    """Test error when domain parameter is missing."""
    action = action_instance(GetMxRecordsAction)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_mx_records_nxdomain(action_instance):
    """NXDOMAIN on MX lookup is a successful not-found."""
    action = action_instance(GetMxRecordsAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NXDOMAIN())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="nonexistent.invalid")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "nonexistent.invalid"
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_get_mx_records_no_answer(action_instance):
    """NoAnswer on MX lookup is a successful not-found with empty records."""
    action = action_instance(GetMxRecordsAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NoAnswer())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "example.com"
    assert result["mx_records"] == []


# ============================================================================
# GetTxtRecordsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_txt_records_success(action_instance):
    """Test successful TXT record retrieval."""
    action = action_instance(GetTxtRecordsAction)

    # Mock TXT records (SPF example)
    txt1 = MagicMock()
    txt1.strings = [b"v=spf1 include:_spf.google.com ~all"]

    txt2 = MagicMock()
    txt2.strings = [b"google-site-verification=", b"ABC123"]

    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter([txt1, txt2])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="google.com")

    assert result["status"] == "success"
    assert result["domain"] == "google.com"
    assert len(result["txt_records"]) == 2
    assert "v=spf1" in result["txt_records"][0]


@pytest.mark.asyncio
async def test_get_txt_records_nxdomain(action_instance):
    """NXDOMAIN on TXT lookup is a successful not-found."""
    action = action_instance(GetTxtRecordsAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NXDOMAIN())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="nonexistent.invalid")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "nonexistent.invalid"
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_get_txt_records_no_answer(action_instance):
    """NoAnswer on TXT lookup is a successful not-found with empty records."""
    action = action_instance(GetTxtRecordsAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NoAnswer())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "example.com"
    assert result["txt_records"] == []


# ============================================================================
# GetNsRecordsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_ns_records_success(action_instance):
    """Test successful NS record retrieval."""
    action = action_instance(GetNsRecordsAction)

    # Mock NS records
    ns1 = MagicMock()
    ns1.target = "ns1.example.com."

    ns2 = MagicMock()
    ns2.target = "ns2.example.com."

    mock_answer = MagicMock()
    mock_answer.__iter__.return_value = iter([ns1, ns2])

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["domain"] == "example.com"
    assert len(result["nameservers"]) == 2
    assert "ns1.example.com" in result["nameservers"]
    assert "ns2.example.com" in result["nameservers"]


@pytest.mark.asyncio
async def test_get_ns_records_missing_parameter(action_instance):
    """Test error when domain parameter is missing."""
    action = action_instance(GetNsRecordsAction)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_ns_records_nxdomain(action_instance):
    """NXDOMAIN on NS lookup is a successful not-found."""
    action = action_instance(GetNsRecordsAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NXDOMAIN())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="nonexistent.invalid")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "nonexistent.invalid"
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_get_ns_records_no_answer(action_instance):
    """NoAnswer on NS lookup is a successful not-found with empty nameservers."""
    action = action_instance(GetNsRecordsAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NoAnswer())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "example.com"
    assert result["nameservers"] == []


# ============================================================================
# GetSoaRecordAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_soa_record_success(action_instance):
    """Test successful SOA record retrieval."""
    action = action_instance(GetSoaRecordAction)

    # Mock SOA record
    soa = MagicMock()
    soa.mname = "ns1.example.com."
    soa.rname = "hostmaster.example.com."
    soa.serial = 2024110401
    soa.refresh = 7200
    soa.retry = 3600
    soa.expire = 1209600
    soa.minimum = 86400

    mock_answer = [soa]  # Only one SOA record

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_answer)

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["domain"] == "example.com"
    assert "soa_record" in result
    assert result["soa_record"]["mname"] == "ns1.example.com"
    assert result["soa_record"]["serial"] == 2024110401


@pytest.mark.asyncio
async def test_get_soa_record_nxdomain(action_instance):
    """NXDOMAIN on SOA lookup is a successful not-found."""
    action = action_instance(GetSoaRecordAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NXDOMAIN())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="nonexistent.invalid")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "nonexistent.invalid"
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_get_soa_record_no_answer(action_instance):
    """NoAnswer on SOA lookup is a successful not-found with null record."""
    action = action_instance(GetSoaRecordAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.resolver.NoAnswer())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "example.com"
    assert result["soa_record"] is None


@pytest.mark.asyncio
async def test_get_soa_record_timeout(action_instance):
    """Test timeout error."""
    action = action_instance(GetSoaRecordAction)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=dns.exception.Timeout())

    with patch("dns.asyncresolver.Resolver", return_value=mock_resolver):
        result = await action.execute(domain="example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
