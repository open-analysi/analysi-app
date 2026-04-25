"""Unit tests for AbuseIPDB integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.abuseipdb.actions import (
    HealthCheckAction,
    LookupIpAction,
    ReportIpAction,
    _validate_categories,
    _validate_ip_safe,
)


class TestValidationHelpers:
    """Test IP and category validation helper functions."""

    # IP Validation Tests
    def test_validate_ip_ipv4_valid(self):
        """Test that valid IPv4 addresses are accepted."""
        test_ips = ["8.8.8.8", "192.168.1.1", "127.0.0.1", "10.0.0.1"]
        for ip in test_ips:
            is_valid, error_msg = _validate_ip_safe(ip)
            assert is_valid is True, f"Expected {ip} to be valid"
            assert error_msg == "", f"Expected no error for {ip}"

    def test_validate_ip_ipv6_valid(self):
        """Test that valid IPv6 addresses are accepted."""
        test_ips = [
            "2001:4860:4860::8888",
            "::1",
            "fe80::1",
            "2001:db8::1",
        ]
        for ip in test_ips:
            is_valid, error_msg = _validate_ip_safe(ip)
            assert is_valid is True, f"Expected {ip} to be valid"
            assert error_msg == "", f"Expected no error for {ip}"

    def test_validate_ip_invalid_format(self):
        """Test that malformed IP addresses are rejected with clear error."""
        test_ips = [
            "not.an.ip",
            "999.999.999.999",
            "192.168.1",
            "192.168.1.1.1",
            "invalid",
        ]
        for ip in test_ips:
            is_valid, error_msg = _validate_ip_safe(ip)
            assert is_valid is False, f"Expected {ip} to be invalid"
            assert "Invalid IP address format" in error_msg

    def test_validate_ip_none_or_empty(self):
        """Test that None or empty string is rejected."""
        test_values = [None, "", "   "]
        for value in test_values:
            is_valid, error_msg = _validate_ip_safe(value)
            assert is_valid is False
            assert "IP address is required" in error_msg

    # Category Validation Tests
    def test_validate_categories_valid_format(self):
        """Test that valid comma-separated category IDs are accepted."""
        test_categories = ["4", "4,18", "4,18,22", "3,4,5,6"]
        for categories in test_categories:
            is_valid, error_msg = _validate_categories(categories)
            assert is_valid is True, f"Expected {categories} to be valid"
            assert error_msg == "", f"Expected no error for {categories}"

    def test_validate_categories_invalid_format(self):
        """Test that invalid category formats are rejected."""
        test_categories = ["", "   ", ",", "4,,18", "abc", "4,abc"]
        for categories in test_categories:
            is_valid, error_msg = _validate_categories(categories)
            assert is_valid is False, f"Expected {categories} to be invalid"
            assert (
                "Invalid categories format" in error_msg
                or "Categories are required" in error_msg
            )

    def test_validate_categories_none(self):
        """Test that None is rejected."""
        is_valid, error_msg = _validate_categories(None)
        assert is_valid is False
        assert "Categories are required" in error_msg


class TestHealthCheckAction:
    """Test AbuseIPDB health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="abuseipdb",
            action_id="health_check",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = {"data": {"ipAddress": "127.0.0.1", "abuseConfidenceScore": 0}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert "message" in result

    @pytest.mark.asyncio
    async def test_health_check_uses_127_0_0_1(self, health_check_action):
        """Test health check uses 127.0.0.1 for test (safe IP)."""
        mock_response = {"data": {"ipAddress": "127.0.0.1", "abuseConfidenceScore": 0}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            await health_check_action.execute()

            # Verify 127.0.0.1 was used in the request (GET /check, not POST /report)
            call_args = mock_request.call_args
            assert call_args[1].get("params", {}).get("ipAddress") == "127.0.0.1"

    @pytest.mark.asyncio
    async def test_health_check_missing_api_key(self):
        """Test health check fails gracefully when API key is missing."""
        action = HealthCheckAction(
            integration_id="abuseipdb",
            action_id="health_check",
            settings={},
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing API key" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_api_error(self):
        """Test health check handles API errors (returns unhealthy)."""
        action = HealthCheckAction(
            integration_id="abuseipdb",
            action_id="health_check",
            settings={},
            credentials={"api_key": "invalid-key"},
        )

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "Invalid API key" in result["error"]
        assert result["healthy"] is False


class TestLookupIpAction:
    """Test AbuseIPDB IP lookup action."""

    @pytest.fixture
    def lookup_ip_action(self):
        """Create IP lookup action instance."""
        return LookupIpAction(
            integration_id="abuseipdb",
            action_id="lookup_ip",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_lookup_ip_success_with_reports(self, lookup_ip_action):
        """Test successful IP lookup returns reputation data."""
        mock_response = {
            "data": {
                "ipAddress": "8.8.8.8",
                "abuseConfidenceScore": 25,
                "totalReports": 10,
                "numDistinctUsers": 5,
                "isPublic": True,
                "ipVersion": 4,
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await lookup_ip_action.execute(ip="8.8.8.8", days=10)

        assert result["status"] == "success"
        assert result["ip_address"] == "8.8.8.8"
        assert result["total_reports"] == 10
        assert result["abuse_confidence_score"] == 25
        assert "full_data" in result

    @pytest.mark.asyncio
    async def test_lookup_ip_success_no_reports(self, lookup_ip_action):
        """Test IP with no reports returns empty but successful response."""
        mock_response = {
            "data": {
                "ipAddress": "192.168.1.1",
                "abuseConfidenceScore": 0,
                "totalReports": 0,
                "numDistinctUsers": 0,
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await lookup_ip_action.execute(ip="192.168.1.1", days=30)

        assert result["status"] == "success"
        assert result["total_reports"] == 0

    @pytest.mark.asyncio
    async def test_lookup_ip_ipv6_address(self, lookup_ip_action):
        """Test IPv6 addresses are supported."""
        mock_response = {
            "data": {
                "ipAddress": "2001:4860:4860::8888",
                "abuseConfidenceScore": 0,
                "totalReports": 0,
                "ipVersion": 6,
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await lookup_ip_action.execute(ip="2001:4860:4860::8888")

        assert result["status"] == "success"
        assert result["ip_address"] == "2001:4860:4860::8888"

    @pytest.mark.asyncio
    async def test_lookup_ip_default_days_parameter(self, lookup_ip_action):
        """Test days parameter defaults to 10 if not provided."""
        mock_response = {
            "data": {
                "ipAddress": "8.8.8.8",
                "abuseConfidenceScore": 0,
                "totalReports": 0,
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            await lookup_ip_action.execute(ip="8.8.8.8")

            # Verify default days=10
            call_args = mock_request.call_args
            params = call_args[1].get("params", {})
            assert params["maxAgeInDays"] == 10

    @pytest.mark.asyncio
    async def test_lookup_ip_custom_days_parameter(self, lookup_ip_action):
        """Test custom days parameter is passed correctly."""
        mock_response = {
            "data": {
                "ipAddress": "8.8.8.8",
                "abuseConfidenceScore": 0,
                "totalReports": 0,
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            await lookup_ip_action.execute(ip="8.8.8.8", days=30)

            # Verify custom days=30
            call_args = mock_request.call_args
            params = call_args[1].get("params", {})
            assert params["maxAgeInDays"] == 30

    @pytest.mark.asyncio
    async def test_lookup_ip_parameter_name_variations(self, lookup_ip_action):
        """Test both 'ip' and 'ip_address' parameter names work."""
        mock_response = {
            "data": {
                "ipAddress": "8.8.8.8",
                "abuseConfidenceScore": 0,
                "totalReports": 0,
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            # Test with ip_address parameter
            result = await lookup_ip_action.execute(ip_address="8.8.8.8")
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_lookup_ip_missing_ip(self, lookup_ip_action):
        """Test error when IP parameter is missing."""
        result = await lookup_ip_action.execute()

        assert result["status"] == "error"
        assert "IP address is required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_lookup_ip_invalid_format(self, lookup_ip_action):
        """Test error for invalid IP format."""
        result = await lookup_ip_action.execute(ip="not.an.ip.address")

        assert result["status"] == "error"
        assert "Invalid IP address format" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_lookup_ip_missing_credentials(self):
        """Test error when API key is missing from credentials."""
        action = LookupIpAction(
            integration_id="abuseipdb",
            action_id="lookup_ip",
            settings={},
            credentials={},
        )

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Missing API key" in result["error"]

    @pytest.mark.asyncio
    async def test_lookup_ip_api_error_401(self, lookup_ip_action):
        """Test 401 errors are handled (invalid API key)."""
        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key"),
        ):
            result = await lookup_ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Invalid API key" in result["error"]
        assert result["error_type"] == "Exception"

    @pytest.mark.asyncio
    async def test_lookup_ip_api_error_429(self, lookup_ip_action):
        """Test 429 errors are handled (rate limit)."""
        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await lookup_ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Rate limit exceeded" in result["error"]
        assert result["error_type"] == "Exception"

    @pytest.mark.asyncio
    async def test_lookup_ip_timeout(self, lookup_ip_action):
        """Test timeout errors are handled gracefully."""
        with patch.object(
            lookup_ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Request timed out"),
        ):
            result = await lookup_ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Request timed out" in result["error"]
        assert result["error_type"] == "Exception"


class TestReportIpAction:
    """Test AbuseIPDB IP report action."""

    @pytest.fixture
    def report_ip_action(self):
        """Create IP report action instance."""
        return ReportIpAction(
            integration_id="abuseipdb",
            action_id="report_ip",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_report_ip_success(self, report_ip_action):
        """Test successful IP report returns confirmation."""
        mock_response = {
            "data": {"ipAddress": "192.0.2.1", "abuseConfidenceScore": 100}
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            report_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await report_ip_action.execute(
                ip="192.0.2.1", categories="4,18", comment="Test abuse"
            )

        assert result["status"] == "success"
        assert result["ip_address"] == "192.0.2.1"
        assert "abuse_confidence_score" in result

    @pytest.mark.asyncio
    async def test_report_ip_without_comment(self, report_ip_action):
        """Test comment is optional (defaults to empty string)."""
        mock_response = {"data": {"ipAddress": "192.0.2.1", "abuseConfidenceScore": 0}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            report_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            result = await report_ip_action.execute(ip="192.0.2.1", categories="4")

            assert result["status"] == "success"

            # Verify comment defaults to empty string
            call_args = mock_request.call_args
            data = call_args[1].get("data", {})
            assert data["comment"] == ""

    @pytest.mark.asyncio
    async def test_report_ip_multiple_categories(self, report_ip_action):
        """Test multiple categories are handled correctly."""
        mock_response = {"data": {"ipAddress": "192.0.2.1", "abuseConfidenceScore": 0}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            report_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            await report_ip_action.execute(ip="192.0.2.1", categories="3,4,18,22")

            # Verify categories passed as comma-separated string
            call_args = mock_request.call_args
            data = call_args[1].get("data", {})
            assert data["categories"] == "3,4,18,22"

    @pytest.mark.asyncio
    async def test_report_ip_single_category(self, report_ip_action):
        """Test single category works."""
        mock_response = {"data": {"ipAddress": "192.0.2.1", "abuseConfidenceScore": 0}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            report_ip_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await report_ip_action.execute(ip="192.0.2.1", categories="4")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_report_ip_missing_ip(self, report_ip_action):
        """Test error when IP is missing."""
        result = await report_ip_action.execute(categories="4")

        assert result["status"] == "error"
        assert "IP address is required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_report_ip_invalid_ip_format(self, report_ip_action):
        """Test error for invalid IP format."""
        result = await report_ip_action.execute(ip="999.999.999.999", categories="4")

        assert result["status"] == "error"
        assert "Invalid IP address format" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_report_ip_missing_categories(self, report_ip_action):
        """Test error when categories are missing."""
        result = await report_ip_action.execute(ip="192.0.2.1")

        assert result["status"] == "error"
        assert "Categories are required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_report_ip_invalid_categories_format(self, report_ip_action):
        """Test error for invalid category format."""
        result = await report_ip_action.execute(ip="192.0.2.1", categories="abc,def")

        assert result["status"] == "error"
        assert "Invalid categories format" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_report_ip_empty_categories(self, report_ip_action):
        """Test error for empty categories string."""
        result = await report_ip_action.execute(ip="192.0.2.1", categories="")

        assert result["status"] == "error"
        assert "Categories are required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_report_ip_missing_credentials(self):
        """Test error when API key is missing."""
        action = ReportIpAction(
            integration_id="abuseipdb",
            action_id="report_ip",
            settings={},
            credentials={},
        )

        result = await action.execute(ip="192.0.2.1", categories="4")

        assert result["status"] == "error"
        assert "Missing API key" in result["error"]

    @pytest.mark.asyncio
    async def test_report_ip_api_error_401(self, report_ip_action):
        """Test 401 errors are handled."""
        with patch.object(
            report_ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid API key"),
        ):
            result = await report_ip_action.execute(ip="192.0.2.1", categories="4")

        assert result["status"] == "error"
        assert "Invalid API key" in result["error"]

    @pytest.mark.asyncio
    async def test_report_ip_api_error_429(self, report_ip_action):
        """Test 429 errors are handled."""
        with patch.object(
            report_ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await report_ip_action.execute(ip="192.0.2.1", categories="4")

        assert result["status"] == "error"
        assert "Rate limit exceeded" in result["error"]


# ============================================================================
# STUB ACTIONS (ThreatIntel Archetype Compliance)
# ============================================================================


class TestLookupDomainAction:
    """Tests for LookupDomainAction (stub)."""

    @pytest.fixture
    def lookup_domain_action(self):
        """Create LookupDomainAction instance."""
        from analysi.integrations.framework.integrations.abuseipdb.actions import (
            LookupDomainAction,
        )

        return LookupDomainAction(
            integration_id="abuseipdb",
            action_id="lookup_domain",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_lookup_domain_returns_not_supported(self, lookup_domain_action):
        """Test that domain lookup returns not supported error."""
        result = await lookup_domain_action.execute(domain="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "NotSupportedError"
        assert "not supported" in result["error"].lower()
        assert result["supported_lookups"] == ["ip"]


class TestLookupFileHashAction:
    """Tests for LookupFileHashAction (stub)."""

    @pytest.fixture
    def lookup_file_hash_action(self):
        """Create LookupFileHashAction instance."""
        from analysi.integrations.framework.integrations.abuseipdb.actions import (
            LookupFileHashAction,
        )

        return LookupFileHashAction(
            integration_id="abuseipdb",
            action_id="lookup_file_hash",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_lookup_file_hash_returns_not_supported(
        self, lookup_file_hash_action
    ):
        """Test that file hash lookup returns not supported error."""
        result = await lookup_file_hash_action.execute(
            file_hash="d41d8cd98f00b204e9800998ecf8427e"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "NotSupportedError"
        assert "not supported" in result["error"].lower()
        assert result["supported_lookups"] == ["ip"]


class TestLookupUrlAction:
    """Tests for LookupUrlAction (stub)."""

    @pytest.fixture
    def lookup_url_action(self):
        """Create LookupUrlAction instance."""
        from analysi.integrations.framework.integrations.abuseipdb.actions import (
            LookupUrlAction,
        )

        return LookupUrlAction(
            integration_id="abuseipdb",
            action_id="lookup_url",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_lookup_url_returns_not_supported(self, lookup_url_action):
        """Test that URL lookup returns not supported error."""
        result = await lookup_url_action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "NotSupportedError"
        assert "not supported" in result["error"].lower()
        assert result["supported_lookups"] == ["ip"]
