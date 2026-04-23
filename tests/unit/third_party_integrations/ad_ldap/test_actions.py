"""Unit tests for AD LDAP integration actions."""

import json
from unittest.mock import MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.ad_ldap.actions import (
    GetAttributesAction,
    HealthCheckAction,
    RunQueryAction,
)

# ============================================================================
# TEST CONNECTIVITY ACTION TESTS
# ============================================================================


class TestADLDAPConnectivityAction:
    """Test AD LDAP test connectivity action."""

    @pytest.fixture
    def test_connectivity_action(self):
        """Create HealthCheckAction instance."""
        return HealthCheckAction(
            integration_id="ad_ldap",
            action_id="health_check",
            settings={
                "server": "ad.example.com",
                "force_ssl": True,
                "ssl_port": 636,
                "validate_ssl_cert": False,
                "timeout": 30,
            },
            credentials={
                "username": "admin@example.com",
                "password": "password123",
            },
        )

    @pytest.mark.asyncio
    async def test_connectivity_success(self, test_connectivity_action):
        """Test successful connectivity test."""
        # Mock LDAP connection
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.unbind.return_value = None

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await test_connectivity_action.execute()

        assert result["status"] == "success"
        assert result["message"] == "Test Connectivity Passed"
        assert result["data"]["connected"] is True
        assert result["data"]["server"] == "ad.example.com"

    @pytest.mark.asyncio
    async def test_connectivity_missing_server(self):
        """Test connectivity with missing server."""
        action = HealthCheckAction(
            integration_id="ad_ldap",
            action_id="health_check",
            settings={},
            credentials={
                "username": "admin@example.com",
                "password": "password123",
            },
        )
        # server is now in settings, not credentials

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "server" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connectivity_missing_username(self):
        """Test connectivity with missing username."""
        action = HealthCheckAction(
            integration_id="ad_ldap",
            action_id="health_check",
            settings={"server": "ad.example.com"},
            credentials={
                "password": "password123",
            },
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "username" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connectivity_missing_password(self):
        """Test connectivity with missing password."""
        action = HealthCheckAction(
            integration_id="ad_ldap",
            action_id="health_check",
            settings={"server": "ad.example.com"},
            credentials={
                "username": "admin@example.com",
            },
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "password" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connectivity_bind_failure(self, test_connectivity_action):
        """Test connectivity with bind failure."""
        # Mock LDAP connection that fails to bind
        mock_conn = MagicMock()
        mock_conn.bind.return_value = False
        mock_conn.result = {"description": "Invalid credentials"}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await test_connectivity_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "LDAPException"

    @pytest.mark.asyncio
    async def test_connectivity_ldap_exception(self, test_connectivity_action):
        """Test connectivity with LDAP exception."""
        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                side_effect=Exception("Connection error"),
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await test_connectivity_action.execute()

        assert result["status"] == "error"
        assert "error" in result


# ============================================================================
# GET ATTRIBUTES ACTION TESTS
# ============================================================================


class TestADLDAPGetAttributesAction:
    """Test AD LDAP get attributes action."""

    @pytest.fixture
    def get_attributes_action(self):
        """Create GetAttributesAction instance."""
        return GetAttributesAction(
            integration_id="ad_ldap",
            action_id="get_attributes",
            settings={
                "server": "ad.example.com",
                "force_ssl": True,
                "ssl_port": 636,
                "validate_ssl_cert": False,
                "timeout": 30,
            },
            credentials={
                "username": "admin@example.com",
                "password": "password123",
            },
        )

    @pytest.mark.asyncio
    async def test_get_attributes_success(self, get_attributes_action):
        """Test successful get attributes."""
        # Mock LDAP connection
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.search.return_value = True
        mock_conn.response = [
            {
                "type": "searchResEntry",
                "dn": "CN=TestUser,DC=example,DC=com",
                "attributes": {
                    "sAMAccountName": "testuser",
                    "mail": "test@example.com",
                },
            }
        ]
        mock_conn.response_to_json.return_value = json.dumps(
            {
                "entries": [
                    {
                        "dn": "CN=TestUser,DC=example,DC=com",
                        "attributes": {
                            "sAMAccountName": "testuser",
                            "mail": "test@example.com",
                        },
                    }
                ]
            }
        )
        mock_conn.unbind.return_value = None
        mock_conn.server.info.other = {"defaultNamingContext": ["DC=example,DC=com"]}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await get_attributes_action.execute(
                principals="testuser", attributes="sAMAccountName;mail"
            )

        assert result["status"] == "success"
        assert "data" in result
        assert result["total_objects"] == 1

    @pytest.mark.asyncio
    async def test_get_attributes_missing_principals(self, get_attributes_action):
        """Test get attributes with missing principals parameter."""
        result = await get_attributes_action.execute(attributes="sAMAccountName")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "principals" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_attributes_missing_attributes(self, get_attributes_action):
        """Test get attributes with missing attributes parameter."""
        result = await get_attributes_action.execute(principals="testuser")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "attributes" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_attributes_missing_credentials(self):
        """Test get attributes with missing credentials."""
        action = GetAttributesAction(
            integration_id="ad_ldap",
            action_id="get_attributes",
            settings={},
            credentials={},
        )

        result = await action.execute(
            principals="testuser", attributes="sAMAccountName"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_attributes_bind_failure(self, get_attributes_action):
        """Test get attributes with bind failure."""
        # Mock LDAP connection that fails to bind
        mock_conn = MagicMock()
        mock_conn.bind.return_value = False
        mock_conn.result = {"description": "Invalid credentials"}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await get_attributes_action.execute(
                principals="testuser", attributes="sAMAccountName"
            )

        assert result["status"] == "error"
        assert result["error_type"] == "LDAPException"

    @pytest.mark.asyncio
    async def test_get_attributes_multiple_principals(self, get_attributes_action):
        """Test get attributes with multiple principals."""
        # Mock LDAP connection
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.search.return_value = True
        mock_conn.response = [
            {
                "type": "searchResEntry",
                "dn": "CN=User1,DC=example,DC=com",
                "attributes": {"sAMAccountName": "user1"},
            },
            {
                "type": "searchResEntry",
                "dn": "CN=User2,DC=example,DC=com",
                "attributes": {"sAMAccountName": "user2"},
            },
        ]
        mock_conn.response_to_json.return_value = json.dumps(
            {
                "entries": [
                    {
                        "dn": "CN=User1,DC=example,DC=com",
                        "attributes": {"sAMAccountName": "user1"},
                    },
                    {
                        "dn": "CN=User2,DC=example,DC=com",
                        "attributes": {"sAMAccountName": "user2"},
                    },
                ]
            }
        )
        mock_conn.unbind.return_value = None
        mock_conn.server.info.other = {"defaultNamingContext": ["DC=example,DC=com"]}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await get_attributes_action.execute(
                principals="user1;user2", attributes="sAMAccountName"
            )

        assert result["status"] == "success"
        assert result["total_objects"] == 2


# ============================================================================
# RUN QUERY ACTION TESTS
# ============================================================================


class TestADLDAPRunQueryAction:
    """Test AD LDAP run query action."""

    @pytest.fixture
    def run_query_action(self):
        """Create RunQueryAction instance."""
        return RunQueryAction(
            integration_id="ad_ldap",
            action_id="run_query",
            settings={
                "server": "ad.example.com",
                "force_ssl": True,
                "ssl_port": 636,
                "validate_ssl_cert": False,
                "timeout": 30,
            },
            credentials={
                "username": "admin@example.com",
                "password": "password123",
            },
        )

    @pytest.mark.asyncio
    async def test_run_query_success(self, run_query_action):
        """Test successful LDAP query."""
        # Mock LDAP connection
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.search.return_value = True
        mock_conn.response = [
            {
                "type": "searchResEntry",
                "dn": "CN=TestUser,DC=example,DC=com",
                "attributes": {"sAMAccountName": "testuser"},
            }
        ]
        mock_conn.response_to_json.return_value = json.dumps(
            {
                "entries": [
                    {
                        "dn": "CN=TestUser,DC=example,DC=com",
                        "attributes": {"sAMAccountName": "testuser"},
                    }
                ]
            }
        )
        mock_conn.unbind.return_value = None
        mock_conn.server.info.other = {"defaultNamingContext": ["DC=example,DC=com"]}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await run_query_action.execute(
                filter="(sAMAccountName=testuser)", attributes="sAMAccountName"
            )

        assert result["status"] == "success"
        assert "data" in result
        assert result["total_objects"] == 1
        # Check that attributes are lowercase
        assert "samaccountname" in result["data"]["entries"][0]["attributes"]

    @pytest.mark.asyncio
    async def test_run_query_missing_filter(self, run_query_action):
        """Test run query with missing filter parameter."""
        result = await run_query_action.execute(attributes="sAMAccountName")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "filter" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_query_missing_attributes(self, run_query_action):
        """Test run query with missing attributes parameter."""
        result = await run_query_action.execute(filter="(sAMAccountName=*)")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "attributes" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_query_missing_credentials(self):
        """Test run query with missing credentials."""
        action = RunQueryAction(
            integration_id="ad_ldap",
            action_id="run_query",
            settings={},
            credentials={},
        )

        result = await action.execute(
            filter="(sAMAccountName=*)", attributes="sAMAccountName"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_query_bind_failure(self, run_query_action):
        """Test run query with bind failure."""
        # Mock LDAP connection that fails to bind
        mock_conn = MagicMock()
        mock_conn.bind.return_value = False
        mock_conn.result = {"description": "Invalid credentials"}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await run_query_action.execute(
                filter="(sAMAccountName=*)", attributes="sAMAccountName"
            )

        assert result["status"] == "error"
        assert result["error_type"] == "LDAPException"

    @pytest.mark.asyncio
    async def test_run_query_with_search_base(self, run_query_action):
        """Test run query with custom search base."""
        # Mock LDAP connection
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.search.return_value = True
        mock_conn.response = [
            {
                "type": "searchResEntry",
                "dn": "CN=TestUser,OU=Users,DC=example,DC=com",
                "attributes": {"sAMAccountName": "testuser"},
            }
        ]
        mock_conn.response_to_json.return_value = json.dumps(
            {
                "entries": [
                    {
                        "dn": "CN=TestUser,OU=Users,DC=example,DC=com",
                        "attributes": {"sAMAccountName": "testuser"},
                    }
                ]
            }
        )
        mock_conn.unbind.return_value = None

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await run_query_action.execute(
                filter="(sAMAccountName=*)",
                attributes="sAMAccountName",
                search_base="OU=Users,DC=example,DC=com",
            )

        assert result["status"] == "success"
        assert result["total_objects"] == 1

    @pytest.mark.asyncio
    async def test_run_query_ldap_exception(self, run_query_action):
        """Test run query with LDAP exception during query."""
        # Mock LDAP connection that succeeds bind but fails query
        mock_conn = MagicMock()
        mock_conn.bind.return_value = True
        mock_conn.search.side_effect = Exception("LDAP query error")
        mock_conn.server.info.other = {"defaultNamingContext": ["DC=example,DC=com"]}

        with (
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Server"),
            patch(
                "analysi.integrations.framework.integrations.ad_ldap.actions.Connection",
                return_value=mock_conn,
            ),
            patch("analysi.integrations.framework.integrations.ad_ldap.actions.Tls"),
        ):
            result = await run_query_action.execute(
                filter="(sAMAccountName=*)", attributes="sAMAccountName"
            )

        assert result["status"] == "error"
        assert result["error_type"] == "LDAPException"
