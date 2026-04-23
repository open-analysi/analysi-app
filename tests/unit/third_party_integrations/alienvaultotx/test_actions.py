"""Unit tests for AlienVault OTX integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.alienvaultotx.actions import (
    DomainReputationAction,
    FileReputationAction,
    GetPulseAction,
    HealthCheckAction,
    IpReputationAction,
    UrlReputationAction,
    _validate_domain_safe,
    _validate_hash_safe,
    _validate_ip_safe,
    _validate_response_type,
    _validate_url_safe,
)


class TestValidationHelpers:
    """Test validation helper functions."""

    # IP Validation Tests
    def test_validate_ip_ipv4_valid(self):
        """Test that valid IPv4 addresses are accepted."""
        test_ips = ["8.8.8.8", "192.168.1.1", "127.0.0.1", "10.0.0.1"]
        for ip in test_ips:
            is_valid, error_msg, ip_version = _validate_ip_safe(ip)
            assert is_valid is True, f"Expected {ip} to be valid"
            assert error_msg == "", f"Expected no error for {ip}"
            assert ip_version == "ipv4", f"Expected {ip} to be IPv4"

    def test_validate_ip_ipv6_valid(self):
        """Test that valid IPv6 addresses are accepted."""
        test_ips = [
            "2001:4860:4860::8888",
            "::1",
            "fe80::1",
            "2001:db8::1",
        ]
        for ip in test_ips:
            is_valid, error_msg, ip_version = _validate_ip_safe(ip)
            assert is_valid is True, f"Expected {ip} to be valid"
            assert error_msg == "", f"Expected no error for {ip}"
            assert ip_version == "ipv6", f"Expected {ip} to be IPv6"

    def test_validate_ip_invalid_format(self):
        """Test that malformed IP addresses are rejected."""
        test_ips = ["not.an.ip", "999.999.999.999", "192.168.1", "invalid"]
        for ip in test_ips:
            is_valid, error_msg, ip_version = _validate_ip_safe(ip)
            assert is_valid is False, f"Expected {ip} to be invalid"
            assert "Malformed IP" in error_msg
            assert ip_version is None

    def test_validate_ip_none_or_empty(self):
        """Test that None or empty string is rejected."""
        test_values = [None, ""]
        for value in test_values:
            is_valid, error_msg, ip_version = _validate_ip_safe(value)
            assert is_valid is False
            assert "non-empty string" in error_msg
            assert ip_version is None

    # Domain Validation Tests
    def test_validate_domain_valid(self):
        """Test that valid domains are accepted."""
        test_domains = ["example.com", "test.example.com", "malware.test"]
        for domain in test_domains:
            is_valid, error_msg = _validate_domain_safe(domain)
            assert is_valid is True, f"Expected {domain} to be valid"
            assert error_msg == ""

    def test_validate_domain_invalid(self):
        """Test that invalid domains are rejected."""
        test_domains = ["not a domain", "", "192.168.1.1"]
        for domain in test_domains:
            is_valid, error_msg = _validate_domain_safe(domain)
            assert is_valid is False

    # Hash Validation Tests
    def test_validate_hash_md5_valid(self):
        """Test that valid MD5 hashes are accepted."""
        md5_hash = "d41d8cd98f00b204e9800998ecf8427e"
        is_valid, error_msg = _validate_hash_safe(md5_hash)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_hash_sha1_valid(self):
        """Test that valid SHA1 hashes are accepted."""
        sha1_hash = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        is_valid, error_msg = _validate_hash_safe(sha1_hash)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_hash_sha256_valid(self):
        """Test that valid SHA256 hashes are accepted."""
        sha256_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        is_valid, error_msg = _validate_hash_safe(sha256_hash)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_hash_invalid_length(self):
        """Test that hashes with invalid lengths are rejected."""
        invalid_hashes = ["abc123", "a" * 50]
        for hash_val in invalid_hashes:
            is_valid, error_msg = _validate_hash_safe(hash_val)
            assert is_valid is False
            assert "MD5" in error_msg or "SHA" in error_msg

    def test_validate_hash_invalid_chars(self):
        """Test that hashes with non-hex characters are rejected."""
        invalid_hash = "g" * 32  # Invalid MD5
        is_valid, error_msg = _validate_hash_safe(invalid_hash)
        assert is_valid is False
        assert "hexadecimal" in error_msg

    # URL Validation Tests
    def test_validate_url_valid(self):
        """Test that valid URLs are accepted."""
        test_urls = ["https://example.com", "http://test.com/path"]
        for url in test_urls:
            is_valid, error_msg = _validate_url_safe(url)
            assert is_valid is True
            assert error_msg == ""

    def test_validate_url_invalid(self):
        """Test that invalid URLs are rejected."""
        test_urls = ["not a url", "", "ftp://unsupported"]
        for url in test_urls:
            is_valid, error_msg = _validate_url_safe(url)
            assert is_valid is False

    # Response Type Validation Tests
    def test_validate_response_type_valid(self):
        """Test that valid response types are accepted."""
        valid_types = ["general", "geo", "malware"]
        is_valid, error_msg = _validate_response_type("general", valid_types)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_response_type_invalid(self):
        """Test that invalid response types are rejected."""
        valid_types = ["general", "geo"]
        is_valid, error_msg = _validate_response_type("invalid", valid_types)
        assert is_valid is False
        assert "Invalid response type" in error_msg


class TestHealthCheckAction:
    """Test AlienVault OTX health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="alienvaultotx",
            action_id="health_check",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = {"username": "test-user"}

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
        assert result["data"]["healthy"] is True
        assert "message" in result

    @pytest.mark.asyncio
    async def test_health_check_missing_api_key(self):
        """Test health check fails when API key is missing."""
        action = HealthCheckAction(
            integration_id="alienvaultotx",
            action_id="health_check",
            settings={},
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing API key" in result["error"]
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_api_error(self):
        """Test health check handles API errors."""
        action = HealthCheckAction(
            integration_id="alienvaultotx",
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
        assert result["data"]["healthy"] is False


class TestDomainReputationAction:
    """Test AlienVault OTX domain reputation action."""

    @pytest.fixture
    def domain_reputation_action(self):
        """Create domain reputation action instance."""
        return DomainReputationAction(
            integration_id="alienvaultotx",
            action_id="domain_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_domain_reputation_success(self, domain_reputation_action):
        """Test successful domain reputation lookup."""
        mock_response = {
            "pulse_info": {
                "pulses": [
                    {"name": "Malware Campaign", "id": "123"},
                    {"name": "Phishing", "id": "456"},
                ]
            }
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            domain_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await domain_reputation_action.execute(domain="malware.com")

        assert result["status"] == "success"
        assert result["domain"] == "malware.com"
        assert result["num_pulses"] == 2
        assert "pulse_info" in result

    @pytest.mark.asyncio
    async def test_domain_reputation_custom_response_type(
        self, domain_reputation_action
    ):
        """Test domain reputation with custom response type."""
        mock_response = {"pulse_info": {"pulses": []}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            domain_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            result = await domain_reputation_action.execute(
                domain="example.com", response_type="geo"
            )

            assert result["status"] == "success"
            assert result["response_type"] == "geo"

            # Verify the endpoint includes the response type
            call_args = mock_request.call_args
            endpoint = call_args[0][0]
            assert "example.com/geo" in endpoint

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_domain(self, domain_reputation_action):
        """Test error when domain is missing."""
        result = await domain_reputation_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_invalid_domain(self, domain_reputation_action):
        """Test error for invalid domain format."""
        result = await domain_reputation_action.execute(domain="not a domain")

        assert result["status"] == "error"
        assert "Malformed domain" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_invalid_response_type(
        self, domain_reputation_action
    ):
        """Test error for invalid response type."""
        result = await domain_reputation_action.execute(
            domain="example.com", response_type="invalid"
        )

        assert result["status"] == "error"
        assert "Invalid response type" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_api_key(self):
        """Test error when API key is missing."""
        action = DomainReputationAction(
            integration_id="alienvaultotx",
            action_id="domain_reputation",
            settings={},
            credentials={},
        )

        result = await action.execute(domain="example.com")

        assert result["status"] == "error"
        assert "Missing API key" in result["error"]


class TestIpReputationAction:
    """Test AlienVault OTX IP reputation action."""

    @pytest.fixture
    def ip_reputation_action(self):
        """Create IP reputation action instance."""
        return IpReputationAction(
            integration_id="alienvaultotx",
            action_id="ip_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_ip_reputation_ipv4_success(self, ip_reputation_action):
        """Test successful IPv4 reputation lookup."""
        mock_response = {
            "pulse_info": {"pulses": [{"name": "Malicious IP", "id": "789"}]}
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            ip_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await ip_reputation_action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["ip"] == "8.8.8.8"
        assert result["ip_version"] == "ipv4"
        assert result["num_pulses"] == 1

    @pytest.mark.asyncio
    async def test_ip_reputation_ipv6_success(self, ip_reputation_action):
        """Test successful IPv6 reputation lookup."""
        mock_response = {"pulse_info": {"pulses": []}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            ip_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ) as mock_request:
            result = await ip_reputation_action.execute(ip="2001:4860:4860::8888")

            assert result["status"] == "success"
            assert result["ip_version"] == "ipv6"

            # Verify IPv6 endpoint was used
            call_args = mock_request.call_args
            endpoint = call_args[0][0]
            assert "IPv6" in endpoint

    @pytest.mark.asyncio
    async def test_ip_reputation_invalid_ip(self, ip_reputation_action):
        """Test error for invalid IP address."""
        result = await ip_reputation_action.execute(ip="999.999.999.999")

        assert result["status"] == "error"
        assert "Malformed IP" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_ip_reputation_missing_ip(self, ip_reputation_action):
        """Test error when IP is missing."""
        result = await ip_reputation_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestFileReputationAction:
    """Test AlienVault OTX file reputation action."""

    @pytest.fixture
    def file_reputation_action(self):
        """Create file reputation action instance."""
        return FileReputationAction(
            integration_id="alienvaultotx",
            action_id="file_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_file_reputation_md5_success(self, file_reputation_action):
        """Test successful MD5 hash reputation lookup."""
        mock_response = {"pulse_info": {"pulses": [{"name": "Malware", "id": "abc"}]}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            file_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await file_reputation_action.execute(
                hash="d41d8cd98f00b204e9800998ecf8427e"
            )

        assert result["status"] == "success"
        assert result["num_pulses"] == 1

    @pytest.mark.asyncio
    async def test_file_reputation_sha256_success(self, file_reputation_action):
        """Test successful SHA256 hash reputation lookup."""
        mock_response = {"pulse_info": {"pulses": []}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            file_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await file_reputation_action.execute(
                hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            )

        assert result["status"] == "success"
        assert result["num_pulses"] == 0

    @pytest.mark.asyncio
    async def test_file_reputation_invalid_hash(self, file_reputation_action):
        """Test error for invalid hash format."""
        result = await file_reputation_action.execute(hash="invalid")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_file_reputation_missing_hash(self, file_reputation_action):
        """Test error when hash is missing."""
        result = await file_reputation_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestUrlReputationAction:
    """Test AlienVault OTX URL reputation action."""

    @pytest.fixture
    def url_reputation_action(self):
        """Create URL reputation action instance."""
        return UrlReputationAction(
            integration_id="alienvaultotx",
            action_id="url_reputation",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_url_reputation_success(self, url_reputation_action):
        """Test successful URL reputation lookup."""
        mock_response = {"pulse_info": {"pulses": [{"name": "Phishing", "id": "xyz"}]}}

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            url_reputation_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await url_reputation_action.execute(url="https://malicious.com")

        assert result["status"] == "success"
        assert result["url"] == "https://malicious.com"
        assert result["num_pulses"] == 1

    @pytest.mark.asyncio
    async def test_url_reputation_invalid_url(self, url_reputation_action):
        """Test error for invalid URL format."""
        result = await url_reputation_action.execute(url="not a url")

        assert result["status"] == "error"
        assert "Invalid URL" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_url_reputation_missing_url(self, url_reputation_action):
        """Test error when URL is missing."""
        result = await url_reputation_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


class TestGetPulseAction:
    """Test AlienVault OTX get pulse action."""

    @pytest.fixture
    def get_pulse_action(self):
        """Create get pulse action instance."""
        return GetPulseAction(
            integration_id="alienvaultotx",
            action_id="get_pulse",
            settings={},
            credentials={"api_key": "test-api-key"},
        )

    @pytest.mark.asyncio
    async def test_get_pulse_success(self, get_pulse_action):
        """Test successful pulse retrieval."""
        mock_response = {
            "id": "test-pulse-id",
            "name": "Test Pulse",
            "description": "Test description",
            "indicators": [
                {"indicator": "8.8.8.8", "type": "IPv4"},
                {"indicator": "malware.com", "type": "domain"},
            ],
        }

        mock_http_response = MagicMock()
        mock_http_response.json.return_value = mock_response

        with patch.object(
            get_pulse_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_http_response,
        ):
            result = await get_pulse_action.execute(pulse_id="test-pulse-id")

        assert result["status"] == "success"
        assert result["pulse_id"] == "test-pulse-id"
        assert result["num_indicators"] == 2
        assert result["pulse_name"] == "Test Pulse"

    @pytest.mark.asyncio
    async def test_get_pulse_not_found(self, get_pulse_action):
        """Test not-found returns success with not_found flag (not error)."""
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_resp
        )
        with patch.object(
            get_pulse_action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await get_pulse_action.execute(pulse_id="unknown-id")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_get_pulse_missing_pulse_id(self, get_pulse_action):
        """Test error when pulse_id is missing."""
        result = await get_pulse_action.execute()

        assert result["status"] == "error"
        assert "pulse_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_pulse_invalid_pulse_id_type(self, get_pulse_action):
        """Test error when pulse_id is not a string."""
        result = await get_pulse_action.execute(pulse_id=123)

        assert result["status"] == "error"
        assert "pulse_id" in result["error"]
        assert result["error_type"] == "ValidationError"
