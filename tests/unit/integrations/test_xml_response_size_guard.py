"""Regression tests for XML response size guards.

Palo Alto and Exchange integrations parse XML with xmltodict.parse().
Without a response size cap, a malicious or compromised upstream endpoint
can return oversized XML and force high memory/CPU usage (DoS).

These tests verify the 10 MB size guard is enforced before parsing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_http_client(response_text: str):
    """Create a mock httpx.AsyncClient with proper async context manager."""
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    # CRITICAL: __aexit__ must return False to NOT suppress exceptions
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return mock_client


class TestPaloAltoXmlSizeGuard:
    """Verify Palo Alto actions reject oversized XML responses."""

    @pytest.mark.asyncio
    async def test_get_key_rejects_oversized_xml(self):
        """get_key() must reject XML responses exceeding the size limit."""
        from analysi.integrations.framework.integrations.paloalto_firewall.actions import (
            _MAX_XML_RESPONSE_BYTES,
            PaloAltoAPIClient,
        )

        client = PaloAltoAPIClient.__new__(PaloAltoAPIClient)
        client.base_url = "https://firewall/api"
        client.username = "admin"
        client.password = "secret"
        client.timeout = 30
        client.verify = False
        client.api_key = None
        client.major_version = None
        client._http_request = None

        oversized_xml = (
            "<response>" + "x" * (_MAX_XML_RESPONSE_BYTES + 1) + "</response>"
        )
        mock_client = _make_mock_http_client(oversized_xml)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_key()

        assert result["status"] == "error"
        assert "byte limit" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_make_rest_call_rejects_oversized_xml(self):
        """make_rest_call() must reject XML responses exceeding the size limit."""
        from analysi.integrations.framework.integrations.paloalto_firewall.actions import (
            _MAX_XML_RESPONSE_BYTES,
            PaloAltoAPIClient,
        )

        client = PaloAltoAPIClient.__new__(PaloAltoAPIClient)
        client.base_url = "https://firewall/api"
        client.timeout = 30
        client.verify = False
        client.api_key = None
        client.major_version = None
        client._http_request = None

        oversized_xml = (
            "<response>" + "x" * (_MAX_XML_RESPONSE_BYTES + 1) + "</response>"
        )
        mock_client = _make_mock_http_client(oversized_xml)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.make_rest_call({"type": "op", "cmd": "<show></show>"})

        assert result["status"] == "error"
        assert "byte limit" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_normal_xml_response_accepted(self):
        """Normal-sized XML responses should be parsed successfully."""
        from analysi.integrations.framework.integrations.paloalto_firewall.actions import (
            PaloAltoAPIClient,
        )

        client = PaloAltoAPIClient.__new__(PaloAltoAPIClient)
        client.base_url = "https://firewall/api"
        client.timeout = 30
        client.verify = False
        client.api_key = None
        client.major_version = None
        client._http_request = None

        normal_xml = (
            '<response status="success"><result><key>API_KEY</key></result></response>'
        )
        mock_client = _make_mock_http_client(normal_xml)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.make_rest_call({"type": "op", "cmd": "<show></show>"})

        assert result["status"] == "success"


class TestExchangeXmlSizeGuard:
    """Verify Exchange EWS actions reject oversized XML responses."""

    @pytest.mark.asyncio
    async def test_ews_request_rejects_oversized_xml(self):
        """make_ews_request() must reject XML responses exceeding the size limit."""
        from lxml.builder import ElementMaker

        from analysi.integrations.framework.integrations.exchange_onprem.actions import (
            _MAX_XML_RESPONSE_BYTES,
            make_ews_request,
        )

        M = ElementMaker(
            namespace="http://schemas.microsoft.com/exchange/services/2006/messages"
        )
        soap_body = M.ResolveNames(M.UnresolvedEntry("test@example.com"))

        oversized_xml = (
            "<s:Envelope>" + "x" * (_MAX_XML_RESPONSE_BYTES + 1) + "</s:Envelope>"
        )
        mock_client = _make_mock_http_client(oversized_xml)

        with patch("httpx.AsyncClient", return_value=mock_client):
            # The ValueError from the size guard propagates as-is in make_ews_request
            # (only httpx errors and generic Exceptions with specific messages are caught)
            with pytest.raises(ValueError, match="byte limit"):
                await make_ews_request(
                    url="https://exchange/ews",
                    username="admin",
                    password="secret",
                    soap_body=soap_body,
                    version="2016",
                )

    @pytest.mark.asyncio
    async def test_ews_normal_response_accepted(self):
        """Normal-sized EWS responses should be parsed successfully."""
        from lxml.builder import ElementMaker

        from analysi.integrations.framework.integrations.exchange_onprem.actions import (
            make_ews_request,
        )

        M = ElementMaker(
            namespace="http://schemas.microsoft.com/exchange/services/2006/messages"
        )
        soap_body = M.ResolveNames(M.UnresolvedEntry("test@example.com"))

        normal_xml = """<?xml version="1.0"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
            <s:Body>
                <m:ResolveNamesResponse xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages">
                    <m:ResponseMessages>
                        <m:ResolveNamesResponseMessage>
                            <m:ResolutionSet/>
                        </m:ResolveNamesResponseMessage>
                    </m:ResponseMessages>
                </m:ResolveNamesResponse>
            </s:Body>
        </s:Envelope>"""

        mock_client = _make_mock_http_client(normal_xml)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await make_ews_request(
                url="https://exchange/ews",
                username="admin",
                password="secret",
                soap_body=soap_body,
                version="2016",
            )

        assert isinstance(result, dict)


class TestSizeGuardConstants:
    """Verify size guard constants are consistent across integrations."""

    def test_paloalto_limit_is_10mb(self):
        from analysi.integrations.framework.integrations.paloalto_firewall.actions import (
            _MAX_XML_RESPONSE_BYTES,
        )

        assert _MAX_XML_RESPONSE_BYTES == 10 * 1024 * 1024

    def test_exchange_limit_is_10mb(self):
        from analysi.integrations.framework.integrations.exchange_onprem.actions import (
            _MAX_XML_RESPONSE_BYTES,
        )

        assert _MAX_XML_RESPONSE_BYTES == 10 * 1024 * 1024
