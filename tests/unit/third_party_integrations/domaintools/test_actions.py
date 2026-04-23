"""Unit tests for DomainTools integration actions."""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.integrations.framework.integrations.domaintools.actions import (
    BrandMonitorAction,
    DomainReputationAction,
    HealthCheckAction,
    HostingHistoryAction,
    ReverseLookupDomainAction,
    ReverseLookupIpAction,
    ReverseWhoisEmailAction,
    WhoisDomainAction,
    WhoisHistoryAction,
    WhoisIpAction,
)

# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheckAction:
    """Test DomainTools health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="domaintools",
            action_id="health_check",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_response = {"registrant": "Google LLC", "created_date": "1997-09-15"}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "test_domain" in result["data"]

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self):
        """Test health check with missing credentials."""
        action = HealthCheckAction(
            integration_id="domaintools",
            action_id="health_check",
            settings={"timeout": 30},
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, health_check_action):
        """Test health check with API error."""
        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            side_effect=Exception("API connection failed"),
        ):
            result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "API connection failed" in result["error"]
        assert result["data"]["healthy"] is False


# ============================================================================
# DOMAIN REPUTATION TESTS
# ============================================================================


class TestDomainReputationAction:
    """Test DomainTools domain reputation action."""

    @pytest.fixture
    def domain_reputation_action(self):
        """Create domain reputation action instance."""
        return DomainReputationAction(
            integration_id="domaintools",
            action_id="domain_reputation",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_domain_reputation_success(self, domain_reputation_action):
        """Test successful domain reputation lookup."""
        mock_response = {
            "risk_score": 25,
            "domain": "example.com",
            "components": [{"name": "proximity", "risk_score": 10}],
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await domain_reputation_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["domain"] == "example.com"
        assert result["risk_score"] == 25
        assert "reputation_data" in result

    @pytest.mark.asyncio
    async def test_domain_reputation_with_risk_api(self, domain_reputation_action):
        """Test domain reputation with risk API."""
        mock_response = {"risk_score": 75, "evidence": []}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await domain_reputation_action.execute(
                domain="malicious.com", use_risk_api=True
            )

        assert result["status"] == "success"
        assert result["risk_score"] == 75

    @pytest.mark.asyncio
    async def test_domain_reputation_invalid_domain(self, domain_reputation_action):
        """Test domain reputation with invalid domain."""
        result = await domain_reputation_action.execute(domain="not-a-valid-domain!!!")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_credentials(self):
        """Test domain reputation with missing credentials."""
        action = DomainReputationAction(
            integration_id="domaintools",
            action_id="domain_reputation",
            settings={"timeout": 30},
            credentials={},
        )

        result = await action.execute(domain="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# WHOIS DOMAIN TESTS
# ============================================================================


class TestWhoisDomainAction:
    """Test DomainTools WHOIS domain action."""

    @pytest.fixture
    def whois_domain_action(self):
        """Create WHOIS domain action instance."""
        return WhoisDomainAction(
            integration_id="domaintools",
            action_id="whois_domain",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_whois_domain_success(self, whois_domain_action):
        """Test successful WHOIS domain lookup."""
        mock_response = {
            "registrant": "Google LLC",
            "created_date": "1997-09-15",
            "parsed_whois": {
                "contacts": {"registrant": {"city": "Mountain View", "country": "US"}}
            },
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await whois_domain_action.execute(domain="google.com")

        assert result["status"] == "success"
        assert result["domain"] == "google.com"
        assert "whois_data" in result
        assert result["summary"]["organization"] == "Google LLC"
        assert result["summary"]["city"] == "Mountain View"

    @pytest.mark.asyncio
    async def test_whois_domain_invalid_domain(self, whois_domain_action):
        """Test WHOIS domain with invalid domain."""
        result = await whois_domain_action.execute(domain="")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# WHOIS IP TESTS
# ============================================================================


class TestWhoisIpAction:
    """Test DomainTools WHOIS IP action."""

    @pytest.fixture
    def whois_ip_action(self):
        """Create WHOIS IP action instance."""
        return WhoisIpAction(
            integration_id="domaintools",
            action_id="whois_ip",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_whois_ip_success(self, whois_ip_action):
        """Test successful WHOIS IP lookup."""
        mock_response = {
            "registrant": "Google LLC",
            "parsed_whois": {
                "contacts": {"registrant": {"city": "Mountain View", "country": "US"}}
            },
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await whois_ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["ip"] == "8.8.8.8"
        assert "whois_data" in result
        assert result["summary"]["organization"] == "Google LLC"

    @pytest.mark.asyncio
    async def test_whois_ip_ipv6(self, whois_ip_action):
        """Test WHOIS IP with IPv6 address."""
        mock_response = {"registrant": "Google LLC"}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await whois_ip_action.execute(ip="2001:4860:4860::8888")

        assert result["status"] == "success"
        assert result["ip"] == "2001:4860:4860::8888"

    @pytest.mark.asyncio
    async def test_whois_ip_invalid_ip(self, whois_ip_action):
        """Test WHOIS IP with invalid IP."""
        result = await whois_ip_action.execute(ip="not-an-ip")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# WHOIS HISTORY TESTS
# ============================================================================


class TestWhoisHistoryAction:
    """Test DomainTools WHOIS history action."""

    @pytest.fixture
    def whois_history_action(self):
        """Create WHOIS history action instance."""
        return WhoisHistoryAction(
            integration_id="domaintools",
            action_id="whois_history",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_whois_history_success(self, whois_history_action):
        """Test successful WHOIS history lookup."""
        mock_response = {
            "record_count": 15,
            "history": [
                {"date": "2020-01-01", "registrant": "Old Owner"},
                {"date": "2021-01-01", "registrant": "New Owner"},
            ],
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await whois_history_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["domain"] == "example.com"
        assert result["record_count"] == 15
        assert "history_data" in result

    @pytest.mark.asyncio
    async def test_whois_history_dict_to_list_conversion(self, whois_history_action):
        """Test WHOIS history converts dict to list."""
        mock_response = {
            "record_count": 1,
            "history": {"date": "2020-01-01", "registrant": "Owner"},
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await whois_history_action.execute(domain="example.com")

        assert result["status"] == "success"
        # History should be converted to list
        assert isinstance(result["history_data"]["history"], list)

    @pytest.mark.asyncio
    async def test_whois_history_invalid_domain(self, whois_history_action):
        """Test WHOIS history with invalid domain."""
        result = await whois_history_action.execute(domain="")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# HOSTING HISTORY TESTS
# ============================================================================


class TestHostingHistoryAction:
    """Test DomainTools hosting history action."""

    @pytest.fixture
    def hosting_history_action(self):
        """Create hosting history action instance."""
        return HostingHistoryAction(
            integration_id="domaintools",
            action_id="hosting_history",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_hosting_history_success(self, hosting_history_action):
        """Test successful hosting history lookup."""
        mock_response = {
            "registrar_history": [{"registrar": "GoDaddy", "date": "2020-01-01"}],
            "ip_history": [{"ip": "192.168.1.1", "date": "2020-01-01"}],
            "nameserver_history": [
                {"nameserver": "ns1.example.com", "date": "2020-01-01"}
            ],
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await hosting_history_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["domain"] == "example.com"
        assert result["registrar_history_count"] == 1
        assert result["ip_history_count"] == 1
        assert result["nameserver_history_count"] == 1

    @pytest.mark.asyncio
    async def test_hosting_history_dict_conversion(self, hosting_history_action):
        """Test hosting history converts dicts to lists."""
        mock_response = {
            "registrar_history": {"registrar": "GoDaddy"},
            "ip_history": {"ip": "192.168.1.1"},
            "nameserver_history": {"nameserver": "ns1.example.com"},
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await hosting_history_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert isinstance(result["hosting_data"]["registrar_history"], list)
        assert isinstance(result["hosting_data"]["ip_history"], list)
        assert isinstance(result["hosting_data"]["nameserver_history"], list)


# ============================================================================
# REVERSE LOOKUP DOMAIN TESTS
# ============================================================================


class TestReverseLookupDomainAction:
    """Test DomainTools reverse domain lookup action."""

    @pytest.fixture
    def reverse_lookup_domain_action(self):
        """Create reverse domain lookup action instance."""
        return ReverseLookupDomainAction(
            integration_id="domaintools",
            action_id="reverse_lookup_domain",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_reverse_lookup_domain_success(self, reverse_lookup_domain_action):
        """Test successful reverse domain lookup."""
        mock_response = {"ip_addresses": ["192.168.1.1", "192.168.1.2", "192.168.1.3"]}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reverse_lookup_domain_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["domain"] == "example.com"
        assert result["total_ips"] == 3
        assert len(result["ip_addresses"]) == 3

    @pytest.mark.asyncio
    async def test_reverse_lookup_domain_no_ips(self, reverse_lookup_domain_action):
        """Test reverse domain lookup with no IPs found."""
        mock_response = {}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reverse_lookup_domain_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["total_ips"] == 0

    @pytest.mark.asyncio
    async def test_reverse_lookup_domain_dict_conversion(
        self, reverse_lookup_domain_action
    ):
        """Test reverse domain lookup converts dict to list."""
        mock_response = {"ip_addresses": {"address": "192.168.1.1"}}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reverse_lookup_domain_action.execute(domain="example.com")

        assert result["status"] == "success"
        assert isinstance(result["ip_addresses"], list)


# ============================================================================
# REVERSE LOOKUP IP TESTS
# ============================================================================


class TestReverseLookupIpAction:
    """Test DomainTools reverse IP lookup action."""

    @pytest.fixture
    def reverse_lookup_ip_action(self):
        """Create reverse IP lookup action instance."""
        return ReverseLookupIpAction(
            integration_id="domaintools",
            action_id="reverse_lookup_ip",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_reverse_lookup_ip_success(self, reverse_lookup_ip_action):
        """Test successful reverse IP lookup."""
        mock_response = {
            "ip_addresses": {
                "domain_count": 50,
                "domains": ["example1.com", "example2.com"],
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reverse_lookup_ip_action.execute(ip="192.168.1.1")

        assert result["status"] == "success"
        assert result["ip"] == "192.168.1.1"
        assert result["total_domains"] == 50

    @pytest.mark.asyncio
    async def test_reverse_lookup_ip_invalid_ip(self, reverse_lookup_ip_action):
        """Test reverse IP lookup with invalid IP."""
        result = await reverse_lookup_ip_action.execute(ip="invalid")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# REVERSE WHOIS EMAIL TESTS
# ============================================================================


class TestReverseWhoisEmailAction:
    """Test DomainTools reverse WHOIS email action."""

    @pytest.fixture
    def reverse_whois_email_action(self):
        """Create reverse WHOIS email action instance."""
        return ReverseWhoisEmailAction(
            integration_id="domaintools",
            action_id="reverse_whois_email",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_reverse_whois_email_success(self, reverse_whois_email_action):
        """Test successful reverse WHOIS email lookup."""
        mock_response = {"domains": ["example1.com", "example2.com", "example3.com"]}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reverse_whois_email_action.execute(email="admin@example.com")

        assert result["status"] == "success"
        assert result["email"] == "admin@example.com"
        assert result["total_domains"] == 3
        assert len(result["domains"]) == 3

    @pytest.mark.asyncio
    async def test_reverse_whois_email_count_only(self, reverse_whois_email_action):
        """Test reverse WHOIS email with count_only mode."""
        mock_response = {"domains": []}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            result = await reverse_whois_email_action.execute(
                email="admin@example.com", count_only=True
            )

            # Verify mode parameter was set correctly
            call_args = mock_request.call_args
            assert call_args[1]["data"]["mode"] == "quote"

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_reverse_whois_email_with_history(self, reverse_whois_email_action):
        """Test reverse WHOIS email with history."""
        mock_response = {"domains": ["old-domain.com"]}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            result = await reverse_whois_email_action.execute(
                email="admin@example.com", include_history=True
            )

            # Verify scope parameter was set correctly
            call_args = mock_request.call_args
            assert call_args[1]["data"]["scope"] == "historic"

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_reverse_whois_email_invalid_email(self, reverse_whois_email_action):
        """Test reverse WHOIS email with invalid email."""
        result = await reverse_whois_email_action.execute(email="not-an-email")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# BRAND MONITOR TESTS
# ============================================================================


class TestBrandMonitorAction:
    """Test DomainTools brand monitor action."""

    @pytest.fixture
    def brand_monitor_action(self):
        """Create brand monitor action instance."""
        return BrandMonitorAction(
            integration_id="domaintools",
            action_id="brand_monitor",
            settings={"timeout": 30},
            credentials={"username": "test_user", "api_key": "test_api_key_12345"},
        )

    @pytest.mark.asyncio
    async def test_brand_monitor_success(self, brand_monitor_action):
        """Test successful brand monitor lookup."""
        mock_response = {
            "alerts": [
                {"domain": "example-phish.com", "status": "new"},
                {"domain": "example-fake.com", "status": "new"},
            ]
        }

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await brand_monitor_action.execute()

        assert result["status"] == "success"
        assert result["total_domains"] == 2
        assert len(result["alerts"]) == 2

    @pytest.mark.asyncio
    async def test_brand_monitor_with_status_filter(self, brand_monitor_action):
        """Test brand monitor with status filter."""
        mock_response = {"alerts": []}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            result = await brand_monitor_action.execute(status="new")

            # Verify status is mapped to domain_status
            call_args = mock_request.call_args
            assert "domain_status" in call_args[1]["data"]
            assert call_args[1]["data"]["domain_status"] == "new"

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_brand_monitor_no_alerts(self, brand_monitor_action):
        """Test brand monitor with no alerts."""
        mock_response = {"alerts": []}

        with patch(
            "analysi.integrations.framework.integrations.domaintools.actions._make_domaintools_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await brand_monitor_action.execute()

        assert result["status"] == "success"
        assert result["total_domains"] == 0
