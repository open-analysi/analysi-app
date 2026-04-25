"""Unit tests for WHOIS RDAP integration actions.

The ipwhois library is synchronous; actions wrap it with asyncio.to_thread().
All tests mock _lookup_rdap at the module level to avoid real network calls.
Tests should run in <0.1s per test.
"""

from unittest.mock import patch

import pytest
from ipwhois import IPDefinedError

from analysi.integrations.framework.integrations.whois_rdap.actions import (
    HealthCheckAction,
    WhoisIpAction,
    _is_valid_ip,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_action():
    """Factory fixture that creates an action instance with empty credentials."""

    def _factory(action_class):
        return action_class(
            integration_id="whois-rdap",
            action_id="test_action",
            settings={},
            credentials={},
        )

    return _factory


def _sample_rdap_response(ip: str = "8.8.8.8") -> dict:
    """Return a minimal but realistic RDAP response dict."""
    return {
        "query": ip,
        "asn": "15169",
        "asn_cidr": "8.8.8.0/24",
        "asn_country_code": "US",
        "asn_date": "1992-12-01",
        "asn_description": "GOOGLE, US",
        "asn_registry": "arin",
        "entities": ["GOGL"],
        "network": {
            "cidr": "8.8.8.0/24",
            "country": "US",
            "end_address": "8.8.8.255",
            "start_address": "8.8.8.0",
            "handle": "NET-8-8-8-0-1",
            "ip_version": "v4",
            "name": "GOGL",
        },
        "objects": {
            "GOGL": {
                "handle": "GOGL",
                "contact": {
                    "name": "Google LLC",
                    "kind": "org",
                },
            }
        },
        "nir": None,
    }


# ---------------------------------------------------------------------------
# _is_valid_ip helper tests
# ---------------------------------------------------------------------------


def test_is_valid_ip_v4():
    assert _is_valid_ip("8.8.8.8") is True


def test_is_valid_ip_v6():
    assert _is_valid_ip("2001:4860:4860::8888") is True


def test_is_valid_ip_invalid():
    assert _is_valid_ip("not-an-ip") is False


def test_is_valid_ip_empty():
    assert _is_valid_ip("") is False


# ---------------------------------------------------------------------------
# HealthCheckAction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_success(make_action):
    """Successful health check returns healthy=True and RDAP data."""
    action = make_action(HealthCheckAction)
    response = _sample_rdap_response("8.8.8.8")

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        return_value=response,
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert result["data"]["test_ip"] == "8.8.8.8"
    assert result["data"]["asn"] == "15169"


@pytest.mark.asyncio
async def test_health_check_identity_mismatch(make_action):
    """Health check fails when RDAP response query field does not match 8.8.8.8."""
    action = make_action(HealthCheckAction)
    # Response returns a different IP in the query field
    response = _sample_rdap_response("8.8.8.8")
    response["query"] = "1.1.1.1"

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        return_value=response,
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["error_type"] == "IdentityMismatch"


@pytest.mark.asyncio
async def test_health_check_ip_defined_error(make_action):
    """IPDefinedError during health check returns unhealthy error."""
    action = make_action(HealthCheckAction)

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        side_effect=IPDefinedError("IP is within a special-use range"),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["error_type"] == "IPDefinedError"


@pytest.mark.asyncio
async def test_health_check_generic_exception(make_action):
    """Generic exception during health check returns error."""
    action = make_action(HealthCheckAction)

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        side_effect=Exception("connection refused"),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["error_type"] == "WhoisQueryError"
    assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# WhoisIpAction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whois_ip_success(make_action):
    """Successful lookup returns full RDAP data and a summary."""
    action = make_action(WhoisIpAction)
    response = _sample_rdap_response("8.8.8.8")

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        return_value=response,
    ):
        result = await action.execute(ip="8.8.8.8")

    assert result["status"] == "success"
    assert result["ip"] == "8.8.8.8"

    # Data should be present with objects converted to a list
    data = result["data"]
    assert data["asn"] == "15169"
    assert data["asn_country_code"] == "US"
    assert isinstance(data["objects"], list)
    assert data["objects"][0]["handle"] == "GOGL"

    # Summary fields
    summary = result["summary"]
    assert summary["registry"] == "arin"
    assert summary["asn"] == "15169"
    assert summary["country_code"] == "US"
    assert summary["network"][0]["start_address"] == "8.8.8.0"
    assert summary["network"][0]["end_address"] == "8.8.8.255"


@pytest.mark.asyncio
async def test_whois_ip_v6_success(make_action):
    """IPv6 address lookup works correctly."""
    action = make_action(WhoisIpAction)
    ipv6 = "2001:4860:4860::8888"
    response = _sample_rdap_response(ipv6)
    response["query"] = ipv6

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        return_value=response,
    ):
        result = await action.execute(ip=ipv6)

    assert result["status"] == "success"
    assert result["ip"] == ipv6


@pytest.mark.asyncio
async def test_whois_ip_missing_parameter(make_action):
    """Missing ip parameter returns ValidationError."""
    action = make_action(WhoisIpAction)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "ip" in result["error"]


@pytest.mark.asyncio
async def test_whois_ip_invalid_ip(make_action):
    """Invalid IP string returns ValidationError without hitting the network."""
    action = make_action(WhoisIpAction)

    result = await action.execute(ip="not-an-ip")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid IP address" in result["error"]


@pytest.mark.asyncio
async def test_whois_ip_reserved_ip_returns_not_found(make_action):
    """IPDefinedError (reserved/special-use IP) returns success with not_found=True.

    Treat IPDefinedError as APP_SUCCESS with a message.
    behaviour so Cy scripts do not crash when querying private/reserved IPs.
    """
    action = make_action(WhoisIpAction)

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        side_effect=IPDefinedError("IP is already defined as 'Private-Use'"),
    ):
        result = await action.execute(ip="192.168.1.1")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["ip"] == "192.168.1.1"
    assert "Private-Use" in result["message"]
    assert result["data"] is None


@pytest.mark.asyncio
async def test_whois_ip_query_failure(make_action):
    """Generic exception from RDAP lookup returns error status."""
    action = make_action(WhoisIpAction)

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        side_effect=Exception("network timeout"),
    ):
        result = await action.execute(ip="8.8.8.8")

    assert result["status"] == "error"
    assert result["ip"] == "8.8.8.8"
    assert result["error_type"] == "WhoisQueryError"
    assert "network timeout" in result["error"]


@pytest.mark.asyncio
async def test_whois_ip_no_objects_field(make_action):
    """Response without 'objects' key is handled gracefully."""
    action = make_action(WhoisIpAction)
    response = _sample_rdap_response("1.1.1.1")
    del response["objects"]

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        return_value=response,
    ):
        result = await action.execute(ip="1.1.1.1")

    assert result["status"] == "success"
    assert "objects" not in result["data"]


@pytest.mark.asyncio
async def test_whois_ip_partial_summary(make_action):
    """Summary is built only from fields present in the RDAP response."""
    action = make_action(WhoisIpAction)
    response = {
        "query": "1.1.1.1",
        "asn": "13335",
        # asn_registry and asn_country_code deliberately absent
        # network deliberately absent
    }

    with patch(
        "analysi.integrations.framework.integrations.whois_rdap.actions._lookup_rdap",
        return_value=response,
    ):
        result = await action.execute(ip="1.1.1.1")

    assert result["status"] == "success"
    summary = result["summary"]
    assert summary["asn"] == "13335"
    assert "registry" not in summary
    assert "country_code" not in summary
    assert "network" not in summary
