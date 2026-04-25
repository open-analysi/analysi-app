"""AD LDAP integration actions for Active Directory management.
"""

import asyncio
import json
import ssl
from typing import Any

from ldap3 import ALL, SUBTREE, Connection, Server, Tls

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ATTRIBUTE_SEPARATOR,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_FORCE_SSL,
    DEFAULT_SSL_PORT,
    DEFAULT_VALIDATE_SSL_CERT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_LDAP,
    ERROR_TYPE_VALIDATION,
    MSG_BIND_FAILED,
    MSG_MISSING_ATTRIBUTES,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_FILTER,
    MSG_MISSING_PASSWORD,
    MSG_MISSING_PRINCIPALS,
    MSG_MISSING_SERVER,
    MSG_MISSING_USERNAME,
    SETTINGS_SERVER,
    SETTINGS_SSL,
    SETTINGS_SSL_PORT,
    SETTINGS_VALIDATE_SSL_CERT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# LDAP CONNECTION HELPER
# ============================================================================

async def _ldap_bind(
    server: str,
    username: str,
    password: str,
    use_ssl: bool = DEFAULT_FORCE_SSL,
    ssl_port: int = DEFAULT_SSL_PORT,
    validate_ssl_cert: bool = DEFAULT_VALIDATE_SSL_CERT,
) -> tuple[bool, Connection | None, str]:
    """Bind to LDAP server.

    Args:
        server: LDAP server hostname or IP
        username: Username for binding
        password: Password for binding
        use_ssl: Whether to use SSL
        ssl_port: SSL port number
        validate_ssl_cert: Whether to validate SSL certificate

    Returns:
        Tuple of (success, connection, error_message)
    """

    def sync_bind():
        """Synchronous LDAP bind operation."""
        try:
            # Configure server parameters based on SSL setting
            server_params = {
                "host": server,
                "get_info": ALL,
            }

            if use_ssl:
                # Configure TLS for SSL connections
                if validate_ssl_cert:
                    tls = Tls(validate=ssl.CERT_REQUIRED)
                else:
                    tls = Tls(validate=ssl.CERT_NONE)

                server_params["use_ssl"] = True
                server_params["port"] = ssl_port
                server_params["tls"] = tls
            else:
                # Non-SSL connection - use configured port or default
                server_params["use_ssl"] = False
                server_params["port"] = (
                    ssl_port if ssl_port != DEFAULT_SSL_PORT else 389
                )

            ldap_server = Server(**server_params)

            # Create connection
            ldap_connection = Connection(
                ldap_server, user=username, password=password, raise_exceptions=True
            )

            # Bind to server
            if not ldap_connection.bind():
                error_msg = ldap_connection.result.get("description", MSG_BIND_FAILED)
                return False, None, error_msg

            return True, ldap_connection, ""

        except Exception as e:
            logger.error("ldap_bind_error", error=str(e))
            return False, None, str(e)

    # Run sync operation in thread pool
    try:
        result = await asyncio.to_thread(sync_bind)
        return result
    except Exception as e:
        logger.error("ldap_bind_async_wrapper_error", error=str(e))
        return False, None, str(e)

async def _get_root_dn(connection: Connection) -> str | None:
    """Get root DN from LDAP server.

    Args:
        connection: Active LDAP connection

    Returns:
        Root DN string or None if not found
    """

    def sync_get_root_dn():
        """Synchronous get root DN operation."""
        try:
            return connection.server.info.other["defaultNamingContext"][0]
        except Exception as e:
            logger.error("error_getting_root_dn", error=str(e))
            return None

    try:
        return await asyncio.to_thread(sync_get_root_dn)
    except Exception as e:
        logger.error("get_root_dn_async_wrapper_error", error=str(e))
        return None

async def _get_filtered_response(connection: Connection) -> list[dict]:
    """Get filtered response from LDAP connection.

    Filters out searchResRef entries.

    Args:
        connection: Active LDAP connection

    Returns:
        List of filtered response entries
    """

    def sync_get_filtered():
        """Synchronous get filtered response."""
        try:
            return [i for i in connection.response if i["type"] != "searchResRef"]
        except Exception as e:
            logger.error("error_filtering_response", error=str(e))
            return []

    try:
        return await asyncio.to_thread(sync_get_filtered)
    except Exception as e:
        logger.error("get_filtered_response_async_wrapper_error", error=str(e))
        return []

async def _ldap_query(
    connection: Connection,
    filter_str: str,
    attributes: list[str],
    search_base: str | None = None,
) -> tuple[bool, dict[str, Any], str]:
    """Execute LDAP query.

    Args:
        connection: Active LDAP connection
        filter_str: LDAP filter string
        attributes: List of attributes to retrieve
        search_base: Search base DN (if None, uses root DN)

    Returns:
        Tuple of (success, result_dict, error_message)
    """

    def sync_query():
        """Synchronous LDAP query operation."""
        try:
            # Get search base if not provided
            if search_base is None:
                # Try both camelCase and lowercase variants
                other_info = connection.server.info.other
                if "defaultNamingContext" in other_info:
                    base = other_info["defaultNamingContext"][0]
                elif "defaultnamingcontext" in other_info:
                    base = other_info["defaultnamingcontext"][0]
                else:
                    # Fallback to dc=example,dc=com for OpenLDAP
                    base = "dc=example,dc=com"
            else:
                base = search_base

            # Execute search
            connection.search(
                search_base=base,
                search_filter=filter_str,
                search_scope=SUBTREE,
                attributes=attributes,
            )

            # Get response as JSON
            response_json = connection.response_to_json()
            return True, json.loads(response_json), ""

        except Exception as e:
            logger.error("ldap_query_error", error=str(e))
            return False, {}, str(e)

    try:
        return await asyncio.to_thread(sync_query)
    except Exception as e:
        logger.error("ldap_query_async_wrapper_error", error=str(e))
        return False, {}, str(e)

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for AD LDAP server."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test LDAP connectivity.

        Returns:
            Result with status=success if connected, status=error if failed
        """
        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not server:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_SERVER,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        if not username:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_USERNAME,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        if not password:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PASSWORD,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get settings
        use_ssl = self.settings.get(SETTINGS_SSL, DEFAULT_FORCE_SSL)
        ssl_port = self.settings.get(SETTINGS_SSL_PORT, DEFAULT_SSL_PORT)
        validate_ssl_cert = self.settings.get(
            SETTINGS_VALIDATE_SSL_CERT, DEFAULT_VALIDATE_SSL_CERT
        )

        try:
            # Attempt to bind
            success, connection, error_msg = await _ldap_bind(
                server=server,
                username=username,
                password=password,
                use_ssl=use_ssl,
                ssl_port=ssl_port,
                validate_ssl_cert=validate_ssl_cert,
            )

            if not success:
                return {
                    "healthy": False,
                    "status": STATUS_ERROR,
                    "error": error_msg,
                    "error_type": ERROR_TYPE_LDAP,
                }

            # Close connection
            if connection:
                await asyncio.to_thread(connection.unbind)

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "Test Connectivity Passed",
                "data": {"connected": True, "server": server},
            }

        except Exception as e:
            logger.error("test_connectivity_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetAttributesAction(IntegrationAction):
    """Get attributes of various principals."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get attributes for specified principals.

        Args:
            **kwargs: Must contain:
                - principals: Semi-colon separated list of principals
                - attributes: Semi-colon separated list of attributes

        Returns:
            Result with attribute data or error
        """
        # Validate parameters
        principals_str = kwargs.get("principals")
        attributes_str = kwargs.get("attributes")

        if not principals_str:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_PRINCIPALS,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not attributes_str:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ATTRIBUTES,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not server or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get settings
        use_ssl = self.settings.get(SETTINGS_SSL, DEFAULT_FORCE_SSL)
        ssl_port = self.settings.get(SETTINGS_SSL_PORT, DEFAULT_SSL_PORT)
        validate_ssl_cert = self.settings.get(
            SETTINGS_VALIDATE_SSL_CERT, DEFAULT_VALIDATE_SSL_CERT
        )

        try:
            # Bind to LDAP
            success, connection, error_msg = await _ldap_bind(
                server=server,
                username=username,
                password=password,
                use_ssl=use_ssl,
                ssl_port=ssl_port,
                validate_ssl_cert=validate_ssl_cert,
            )

            if not success:
                return {
                    "status": STATUS_ERROR,
                    "error": error_msg,
                    "error_type": ERROR_TYPE_LDAP,
                }

            # Parse principals and build query
            principal_list = [
                p.strip() for p in principals_str.split(ATTRIBUTE_SEPARATOR)
            ]
            query = "(|"
            for principal in principal_list:
                # Search by multiple attributes to support both AD and OpenLDAP
                query += f"(uid={principal})"  # OpenLDAP/POSIX
                query += f"(cn={principal})"  # Common Name
                query += f"(mail={principal})"  # Email
            query += ")"

            # Parse attributes
            attributes = [a.strip() for a in attributes_str.split(ATTRIBUTE_SEPARATOR)]

            # Execute query
            success, result, error_msg = await _ldap_query(
                connection=connection,
                filter_str=query,
                attributes=attributes,
            )

            if not success:
                await asyncio.to_thread(connection.unbind)
                return {
                    "status": STATUS_ERROR,
                    "error": error_msg,
                    "error_type": ERROR_TYPE_LDAP,
                }

            # Get filtered response count
            filtered_response = await _get_filtered_response(connection)
            total_objects = len(filtered_response)

            # Close connection
            await asyncio.to_thread(connection.unbind)

            return {
                "status": STATUS_SUCCESS,
                "data": result,
                "total_objects": total_objects,
            }

        except Exception as e:
            logger.error("get_attributes_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class RunQueryAction(IntegrationAction):
    """Run arbitrary LDAP query."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute LDAP query.

        Args:
            **kwargs: Must contain:
                - filter: LDAP filter string
                - attributes: Semi-colon separated list of attributes
                - search_base (optional): Search base DN

        Returns:
            Result with query data or error
        """
        # Validate parameters
        filter_str = kwargs.get("filter")
        attributes_str = kwargs.get("attributes")
        search_base = kwargs.get("search_base")

        if not filter_str:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_FILTER,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        if not attributes_str:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_ATTRIBUTES,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate credentials
        server = self.settings.get(SETTINGS_SERVER)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not server or not username or not password:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Get settings
        use_ssl = self.settings.get(SETTINGS_SSL, DEFAULT_FORCE_SSL)
        ssl_port = self.settings.get(SETTINGS_SSL_PORT, DEFAULT_SSL_PORT)
        validate_ssl_cert = self.settings.get(
            SETTINGS_VALIDATE_SSL_CERT, DEFAULT_VALIDATE_SSL_CERT
        )

        try:
            # Bind to LDAP
            success, connection, error_msg = await _ldap_bind(
                server=server,
                username=username,
                password=password,
                use_ssl=use_ssl,
                ssl_port=ssl_port,
                validate_ssl_cert=validate_ssl_cert,
            )

            if not success:
                return {
                    "status": STATUS_ERROR,
                    "error": error_msg,
                    "error_type": ERROR_TYPE_LDAP,
                }

            # Parse attributes
            attributes = [a.strip() for a in attributes_str.split(ATTRIBUTE_SEPARATOR)]

            # Execute query
            success, result, error_msg = await _ldap_query(
                connection=connection,
                filter_str=filter_str,
                attributes=attributes,
                search_base=search_base,
            )

            if not success:
                await asyncio.to_thread(connection.unbind)
                return {
                    "status": STATUS_ERROR,
                    "error": error_msg,
                    "error_type": ERROR_TYPE_LDAP,
                }

            # Unify attributes to lowercase keys
            for i, _ in enumerate(result.get("entries", [])):
                if "attributes" in result["entries"][i]:
                    result["entries"][i]["attributes"] = {
                        k.lower(): v
                        for k, v in result["entries"][i]["attributes"].items()
                    }

            # Get filtered response count
            filtered_response = await _get_filtered_response(connection)
            total_objects = len(filtered_response)

            # Close connection
            await asyncio.to_thread(connection.unbind)

            return {
                "status": STATUS_SUCCESS,
                "data": result,
                "total_objects": total_objects,
            }

        except Exception as e:
            logger.error("run_query_failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
