"""Palo Alto Networks Firewall integration actions.

This module provides actions for managing Palo Alto Networks Firewall including:
- URL/IP/Application blocking and unblocking
- Policy management
- Application listing
- Configuration commits
"""

import hashlib
import ipaddress
import re
from typing import Any

import httpx
import xmltodict

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ADDR_GRP_XPATH,
    APP_GRP_XPATH,
    APP_LIST_XPATH,
    BLOCK_APP_GROUP_NAME,
    BLOCK_IP_GROUP_NAME,
    BLOCK_IP_GROUP_NAME_SRC,
    BLOCK_URL_CAT_NAME,
    BLOCK_URL_PROF_NAME,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    CUSTOM_APP_LIST_XPATH,
    DEFAULT_SOURCE_ADDRESS,
    DEFAULT_TIMEOUT,
    DEFAULT_VSYS,
    DEL_ADDR_GRP_XPATH,
    DEL_APP_XPATH,
    DEL_URL_XPATH,
    ERR_APP_RESPONSE,
    ERR_DEVICE_CONNECTIVITY,
    ERR_INVALID_IP_FORMAT,
    ERR_MISSING_CREDENTIALS,
    ERR_NO_ALLOW_POLICY,
    ERR_NO_POLICY_ENTRIES,
    ERR_PARSE_POLICY_DATA,
    ERR_REPLY_FORMAT_KEY_MISSING,
    ERR_REPLY_NOT_SUCCESS,
    ERR_UNABLE_TO_PARSE_REPLY,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_POLICY,
    ERROR_TYPE_VALIDATION,
    ERROR_TYPE_XML_PARSE,
    IP_ADDR_XPATH,
    MSG_REST_CALL_SUCCEEDED,
    MSG_TEST_CONNECTIVITY_PASSED,
    ADDRESS_NAME_MARKER,
    SEC_POL_APP_TYPE,
    SEC_POL_IP_TYPE,
    SEC_POL_NAME,
    SEC_POL_NAME_SRC,
    SEC_POL_RULES_XPATH,
    SEC_POL_URL_TYPE,
    SEC_POL_XPATH,
    SETTINGS_DEVICE,
    SETTINGS_TIMEOUT,
    SETTINGS_VERIFY_CERT,
    SHOW_SYSTEM_INFO,
    STATUS_ERROR,
    STATUS_SUCCESS,
    TAG_COLOR,
    TAG_CONTAINER_COMMENT,
    TAG_XPATH,
    URL_CAT_XPATH,
    URL_PROF_XPATH,
)

logger = get_logger(__name__)

# Maximum XML response size to parse (10 MB). Prevents DoS from oversized
# responses returned by a compromised or malicious upstream endpoint.
_MAX_XML_RESPONSE_BYTES = 10 * 1024 * 1024

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _is_ip(input_ip_address: str) -> bool:
    """Check if string is a valid IP address."""
    try:
        ipaddress.ip_address(input_ip_address)
        return True
    except ValueError:
        return False

def _get_addr_name(ip: str, ip_type: str) -> str:
    """Generate address name for IP address object."""

    # Remove slash in IP, PAN does not like slash in names
    def rem_slash(x):
        return re.sub(r"(.*)/(.*)", r"\1 mask \2", x)

    if ip_type == "ip-wildcard":

        def rem_slash(x):
            return re.sub(r"(.*)/(.*)", r"\1 wildcard mask \2", x)

    new_ip = ip.replace("-", " - ").replace(":", "-")
    if not new_ip[0].isalnum():
        name = f"{ADDRESS_NAME_MARKER} {rem_slash(new_ip)}"
    else:
        name = f"{rem_slash(new_ip)} {ADDRESS_NAME_MARKER}"

    # Object name can't exceed 63 characters
    if len(name) > 63:
        name = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:-1]

    return name

def _find_ip_type(ip: str) -> str | None:
    """Determine the type of IP address format."""
    if "/" in ip:
        try:
            int(ip.split("/")[1])
            return "ip-netmask"
        except ValueError:
            return "ip-wildcard"
    elif "-" in ip:
        return "ip-range"
    elif _is_ip(ip):
        return "ip-netmask"
    else:
        # Try FQDN
        if re.match(
            r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$",
            ip,
        ):
            return "fqdn"
    return None

# ============================================================================
# PAN-OS API CLIENT
# ============================================================================

class PaloAltoAPIClient:
    """Client for Palo Alto Networks Firewall XML API."""

    def __init__(
        self,
        device: str,
        username: str,
        password: str,
        verify: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        http_request=None,
    ):
        """Initialize API client."""
        self.base_url = f"https://{device}/api/"
        self.username = username
        self.password = password
        self.verify = verify
        self.timeout = timeout
        self.api_key = None
        self.major_version = None
        self._http_request = http_request

    async def get_key(self) -> dict[str, Any]:
        """Generate API key from username/password."""
        data = {"type": "keygen", "user": self.username, "password": self.password}

        try:
            if self._http_request:
                response = await self._http_request(
                    self.base_url,
                    method="POST",
                    data=data,
                    timeout=self.timeout,
                    verify_ssl=self.verify,
                )
                xml = response.text
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout, verify=self.verify
                ) as client:
                    response = await client.post(self.base_url, data=data)
                    response.raise_for_status()
                    xml = response.text

            if len(xml.encode("utf-8")) > _MAX_XML_RESPONSE_BYTES:
                raise ValueError(
                    f"PAN-OS response exceeds {_MAX_XML_RESPONSE_BYTES} byte limit"
                )
            response_dict = xmltodict.parse(xml)

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error getting API key", status_code=e.response.status_code
            )
            return {
                "status": STATUS_ERROR,
                "error": f"{ERR_DEVICE_CONNECTIVITY}: HTTP {e.response.status_code}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except Exception as e:
            logger.error("Error getting API key", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"{ERR_DEVICE_CONNECTIVITY}: {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }

        # Parse response
        response = response_dict.get("response")
        if not response:
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_FORMAT_KEY_MISSING.format(key="response"),
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        status = response.get("@status")
        if not status:
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_FORMAT_KEY_MISSING.format(key="response/status"),
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        if status != "success":
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_NOT_SUCCESS.format(status=status),
                "error_type": ERROR_TYPE_AUTHENTICATION,
            }

        result = response.get("result")
        if not result:
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_FORMAT_KEY_MISSING.format(key="response/result"),
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        key = result.get("key")
        if not key:
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_FORMAT_KEY_MISSING.format(key="response/result/key"),
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        self.api_key = key

        # Validate version
        version_result = await self._validate_version()
        if version_result["status"] != STATUS_SUCCESS:
            return version_result

        return {"status": STATUS_SUCCESS, "message": "API key obtained successfully"}

    async def _validate_version(self) -> dict[str, Any]:
        """Validate device version."""
        data = {"type": "op", "key": self.api_key, "cmd": SHOW_SYSTEM_INFO}

        result = await self.make_rest_call(data)
        if result["status"] != STATUS_SUCCESS:
            return result

        try:
            result_data = result["data"][0]
            device_version = result_data["system"]["sw-version"]
        except (KeyError, IndexError) as e:
            logger.error("Error parsing system info", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": "Unable to parse system info response",
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        if not device_version:
            return {
                "status": STATUS_ERROR,
                "error": "Unable to get version from the device",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        logger.info("Got device version", version=device_version)

        # Extract major version
        try:
            self.major_version = int(device_version.split(".")[0])
        except (ValueError, IndexError):
            self.major_version = 10  # Default to modern version

        return {"status": STATUS_SUCCESS, "version": device_version}

    async def make_rest_call(self, data: dict[str, Any]) -> dict[str, Any]:
        """Make REST API call to PAN-OS."""
        try:
            if self._http_request:
                response = await self._http_request(
                    self.base_url,
                    method="POST",
                    data=data,
                    timeout=self.timeout,
                    verify_ssl=self.verify,
                )
                xml = response.text
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout, verify=self.verify
                ) as client:
                    response = await client.post(self.base_url, data=data)
                    response.raise_for_status()
                    xml = response.text

            if len(xml.encode("utf-8")) > _MAX_XML_RESPONSE_BYTES:
                raise ValueError(
                    f"PAN-OS response exceeds {_MAX_XML_RESPONSE_BYTES} byte limit"
                )
            response_dict = xmltodict.parse(xml)

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error in REST call", status_code=e.response.status_code)
            return {
                "status": STATUS_ERROR,
                "error": f"{ERR_DEVICE_CONNECTIVITY}: HTTP {e.response.status_code}",
                "error_type": ERROR_TYPE_HTTP,
            }
        except xmltodict.expat.ExpatError as e:
            logger.error("XML parse error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"{ERR_UNABLE_TO_PARSE_REPLY}: {e!s}",
                "error_type": ERROR_TYPE_XML_PARSE,
            }
        except Exception as e:
            logger.error("Error in REST call", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"{ERR_DEVICE_CONNECTIVITY}: {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }

        # Parse response
        response = response_dict.get("response")
        if not response:
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_FORMAT_KEY_MISSING.format(key="response"),
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        status = response.get("@status")
        if not status:
            return {
                "status": STATUS_ERROR,
                "error": ERR_REPLY_FORMAT_KEY_MISSING.format(key="response/status"),
                "error_type": ERROR_TYPE_XML_PARSE,
            }

        if status != "success":
            error_msg = ERR_REPLY_NOT_SUCCESS.format(status=status)
            # Add any additional error info from response
            msg = response.get("msg")
            if msg:
                if isinstance(msg, dict):
                    line = msg.get("line")
                    if line:
                        error_msg += f" - {line}"
                elif isinstance(msg, str):
                    error_msg += f" - {msg}"

            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_HTTP,
            }

        result_data = []
        result = response.get("result")
        if result is not None:
            result_data.append(result)

        return {
            "status": STATUS_SUCCESS,
            "message": MSG_REST_CALL_SUCCEEDED,
            "data": result_data,
        }

    async def commit_config(self) -> dict[str, Any]:
        """Commit configuration changes."""
        logger.info("Committing configuration")

        data = {"type": "commit", "cmd": "<commit></commit>", "key": self.api_key}

        result = await self.make_rest_call(data)
        if result["status"] != STATUS_SUCCESS:
            return result

        # Get job ID for commit status polling
        result_data = result.get("data", [])
        if not result_data:
            return {"status": STATUS_SUCCESS, "message": "Commit completed"}

        job_data = result_data[0]
        job_id = job_data.get("job")

        if not job_id:
            return {"status": STATUS_SUCCESS, "message": "Commit completed"}

        logger.info("Commit job started", job_id=job_id)

        # Poll for commit completion
        while True:
            data = {
                "type": "op",
                "key": self.api_key,
                "cmd": f"<show><jobs><id>{job_id}</id></jobs></show>",
            }

            status_result = await self.make_rest_call(data)
            if status_result["status"] != STATUS_SUCCESS:
                # Don't fail if we can't poll status - commit was initiated
                return {
                    "status": STATUS_SUCCESS,
                    "message": "Commit initiated (status check failed)",
                }

            result_data = status_result.get("data", [])
            if result_data:
                job = result_data[0].get("job", {})
                if job.get("status") == "FIN":
                    break

                # Log progress
                progress = job.get("progress", 0)
                logger.info("Commit in progress", progress=progress)

            # Wait before next poll
            import asyncio

            await asyncio.sleep(2)

        return {"status": STATUS_SUCCESS, "message": "Commit completed successfully"}

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Palo Alto Networks Firewall."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test API connectivity and authentication.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "healthy": False,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and test authentication
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        result = await client.get_key()

        if result["status"] == STATUS_SUCCESS:
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_TEST_CONNECTIVITY_PASSED,
                "healthy": True,
            }
        return {
            "status": STATUS_ERROR,
            "error": result.get("error", "Authentication failed"),
            "error_type": result.get("error_type", ERROR_TYPE_AUTHENTICATION),
            "healthy": False,
        }

class BlockUrlAction(IntegrationAction):
    """Block URL by adding to custom URL category and security policy."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block URL in Palo Alto Networks Firewall.

        Args:
            **kwargs: Must contain:
                - url (str): URL to block
                - vsys (str, optional): Virtual system, defaults to vsys1
                - sec_policy (str, optional): Security policy to insert before

        Returns:
            Result with status and details
        """
        # Validate parameters
        url = kwargs.get("url", "").strip()
        if not url:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'url'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        vsys = kwargs.get("vsys", DEFAULT_VSYS)
        sec_policy = kwargs.get("sec_policy")

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Create custom URL category
            logger.info("Creating custom URL category")
            xpath = URL_CAT_XPATH.format(
                vsys=vsys, url_category_name=BLOCK_URL_CAT_NAME
            )
            element = f"<description>Created by Analysi</description><list><member>{url}</member></list><type>URL List</type>"

            data = {
                "type": "config",
                "action": "set",
                "key": client.api_key,
                "xpath": xpath,
                "element": element,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Create URL filtering profile
            logger.info("Adding URL category to URL filtering profile")
            xpath = URL_PROF_XPATH.format(
                vsys=vsys, url_profile_name=BLOCK_URL_PROF_NAME
            )
            element = f"<description>Created by Analysi</description><block><member>{BLOCK_URL_CAT_NAME}</member></block>"

            data = {
                "type": "config",
                "action": "set",
                "key": client.api_key,
                "xpath": xpath,
                "element": element,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Create security policy
            result = await self._add_url_security_policy(client, vsys, sec_policy)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Commit configuration
            commit_result = await client.commit_config()
            if commit_result["status"] != STATUS_SUCCESS:
                return commit_result

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully blocked URL",
                "url": url,
                "vsys": vsys,
            }

        except Exception as e:
            logger.error("Block URL failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Block URL failed: {e!s}",
                "error_type": type(e).__name__,
            }

    async def _add_url_security_policy(
        self, client: PaloAltoAPIClient, vsys: str, sec_policy: str | None
    ) -> dict[str, Any]:
        """Create URL security policy."""
        sec_policy_name = SEC_POL_NAME.format(type=SEC_POL_URL_TYPE)
        allow_rule_name = sec_policy

        # If no policy specified, find first allow policy
        if not allow_rule_name:
            data = {
                "type": "config",
                "action": "get",
                "key": client.api_key,
                "xpath": SEC_POL_RULES_XPATH.format(vsys=vsys),
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Find first allow policy
            result_data = result.get("data", [])
            if not result_data:
                return {
                    "status": STATUS_ERROR,
                    "error": ERR_PARSE_POLICY_DATA,
                    "error_type": ERROR_TYPE_POLICY,
                }

            rules = result_data[0].get("rules", {})
            entries = rules.get("entry")

            if not entries:
                return {
                    "status": STATUS_ERROR,
                    "error": ERR_NO_POLICY_ENTRIES,
                    "error_type": ERROR_TYPE_POLICY,
                }

            # Convert to list if single entry
            if isinstance(entries, dict):
                entries = [entries]

            # Find first allow rule
            allow_rule_name = None
            for entry in entries:
                action = entry.get("action")
                if action and (
                    action == "allow"
                    or (isinstance(action, dict) and action.get("#text") == "allow")
                ):
                    allow_rule_name = entry.get("@name")
                    break

            if not allow_rule_name:
                return {
                    "status": STATUS_ERROR,
                    "error": ERR_NO_ALLOW_POLICY,
                    "error_type": ERROR_TYPE_POLICY,
                }

        # Build security policy element
        element = "<from><member>any</member></from>"
        element += "<to><member>any</member></to>"
        element += "<source><member>any</member></source>"
        element += "<source-user><member>any</member></source-user>"
        element += "<category><member>any</member></category>"
        element += "<service><member>application-default</member></service>"
        element += "<description>Created by Analysi, please don't edit</description>"

        # Add HIP profiles based on version
        if client.major_version and client.major_version > 9:
            element += "<source-hip><member>any</member></source-hip>"
            element += "<destination-hip><member>any</member></destination-hip>"
        else:
            element += "<hip-profiles><member>any</member></hip-profiles>"

        element += "<action>allow</action>"
        element += f"<profile-setting><profiles><url-filtering><member>{BLOCK_URL_PROF_NAME}</member></url-filtering></profiles></profile-setting>"
        element += "<application><member>any</member></application>"
        element += "<destination><member>any</member></destination>"

        xpath = SEC_POL_XPATH.format(vsys=vsys, sec_policy_name=sec_policy_name)
        data = {
            "type": "config",
            "action": "set",
            "key": client.api_key,
            "xpath": xpath,
            "element": element,
        }

        result = await client.make_rest_call(data)
        if result["status"] != STATUS_SUCCESS:
            return result

        # Move policy before allow rule (if not already there)
        if allow_rule_name != sec_policy_name:
            data = {
                "type": "config",
                "action": "move",
                "key": client.api_key,
                "xpath": xpath,
                "where": "before",
                "dst": allow_rule_name,
            }

            move_result = await client.make_rest_call(data)
            # Ignore "already at the top" errors
            if move_result["status"] != STATUS_SUCCESS:
                error_msg = move_result.get("error", "")
                if "already at the top" not in error_msg.lower():
                    return move_result

        return {"status": STATUS_SUCCESS, "message": "Security policy created"}

class UnblockUrlAction(IntegrationAction):
    """Unblock URL by removing from custom URL category."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock URL in Palo Alto Networks Firewall.

        Args:
            **kwargs: Must contain:
                - url (str): URL to unblock
                - vsys (str, optional): Virtual system, defaults to vsys1

        Returns:
            Result with status and details
        """
        # Validate parameters
        url = kwargs.get("url", "").strip()
        if not url:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'url'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        vsys = kwargs.get("vsys", DEFAULT_VSYS)

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Remove URL from category
            logger.info("Removing URL from blocked category")
            xpath = URL_CAT_XPATH.format(
                vsys=vsys, url_category_name=BLOCK_URL_CAT_NAME
            )
            xpath += DEL_URL_XPATH.format(url=url)

            data = {
                "type": "config",
                "action": "delete",
                "key": client.api_key,
                "xpath": xpath,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Commit configuration
            commit_result = await client.commit_config()
            if commit_result["status"] != STATUS_SUCCESS:
                return commit_result

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully unblocked URL",
                "url": url,
                "vsys": vsys,
            }

        except Exception as e:
            logger.error("Unblock URL failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Unblock URL failed: {e!s}",
                "error_type": type(e).__name__,
            }

class BlockApplicationAction(IntegrationAction):
    """Block application by adding to application group and security policy."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block application in Palo Alto Networks Firewall.

        Args:
            **kwargs: Must contain:
                - application (str): Application to block
                - vsys (str, optional): Virtual system, defaults to vsys1

        Returns:
            Result with status and details
        """
        # Validate parameters
        application = kwargs.get("application", "").strip()
        if not application:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'application'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        vsys = kwargs.get("vsys", DEFAULT_VSYS)

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Create application group
            logger.info("Creating application group")
            xpath = APP_GRP_XPATH.format(vsys=vsys, app_group_name=BLOCK_APP_GROUP_NAME)
            element = f"<members><member>{application}</member></members>"

            data = {
                "type": "config",
                "action": "set",
                "key": client.api_key,
                "xpath": xpath,
                "element": element,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Create security policy
            result = await self._add_app_security_policy(client, vsys)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Commit configuration
            commit_result = await client.commit_config()
            if commit_result["status"] != STATUS_SUCCESS:
                return commit_result

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully blocked application",
                "application": application,
                "vsys": vsys,
            }

        except Exception as e:
            logger.error("Block application failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Block application failed: {e!s}",
                "error_type": type(e).__name__,
            }

    async def _add_app_security_policy(
        self, client: PaloAltoAPIClient, vsys: str
    ) -> dict[str, Any]:
        """Create application security policy."""
        sec_policy_name = SEC_POL_NAME.format(type=SEC_POL_APP_TYPE)

        # Build security policy element
        element = "<from><member>any</member></from>"
        element += "<to><member>any</member></to>"
        element += "<source><member>any</member></source>"
        element += "<source-user><member>any</member></source-user>"
        element += "<category><member>any</member></category>"
        element += "<service><member>application-default</member></service>"
        element += "<description>Created by Analysi, please don't edit</description>"

        # Add HIP profiles based on version
        if client.major_version and client.major_version > 9:
            element += "<source-hip><member>any</member></source-hip>"
            element += "<destination-hip><member>any</member></destination-hip>"
        else:
            element += "<hip-profiles><member>any</member></hip-profiles>"

        element += "<action>deny</action>"
        element += f"<application><member>{BLOCK_APP_GROUP_NAME}</member></application>"
        element += "<destination><member>any</member></destination>"

        xpath = SEC_POL_XPATH.format(vsys=vsys, sec_policy_name=sec_policy_name)
        data = {
            "type": "config",
            "action": "set",
            "key": client.api_key,
            "xpath": xpath,
            "element": element,
        }

        result = await client.make_rest_call(data)
        if result["status"] != STATUS_SUCCESS:
            return result

        # Move to top
        data = {
            "type": "config",
            "action": "move",
            "key": client.api_key,
            "xpath": xpath,
            "where": "top",
        }

        move_result = await client.make_rest_call(data)
        # Ignore "already at the top" errors
        if move_result["status"] != STATUS_SUCCESS:
            error_msg = move_result.get("error", "")
            if "already at the top" not in error_msg.lower():
                return move_result

        return {"status": STATUS_SUCCESS, "message": "Security policy created"}

class UnblockApplicationAction(IntegrationAction):
    """Unblock application by removing from application group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock application in Palo Alto Networks Firewall.

        Args:
            **kwargs: Must contain:
                - application (str): Application to unblock
                - vsys (str, optional): Virtual system, defaults to vsys1

        Returns:
            Result with status and details
        """
        # Validate parameters
        application = kwargs.get("application", "").strip()
        if not application:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'application'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        vsys = kwargs.get("vsys", DEFAULT_VSYS)

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Remove application from group
            logger.info("Removing application from blocked group")
            xpath = APP_GRP_XPATH.format(vsys=vsys, app_group_name=BLOCK_APP_GROUP_NAME)
            xpath += DEL_APP_XPATH.format(app_name=application)

            data = {
                "type": "config",
                "action": "delete",
                "key": client.api_key,
                "xpath": xpath,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Commit configuration
            commit_result = await client.commit_config()
            if commit_result["status"] != STATUS_SUCCESS:
                return commit_result

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully unblocked application",
                "application": application,
                "vsys": vsys,
            }

        except Exception as e:
            logger.error("Unblock application failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Unblock application failed: {e!s}",
                "error_type": type(e).__name__,
            }

class BlockIpAction(IntegrationAction):
    """Block IP address by adding to address group and security policy."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block IP address in Palo Alto Networks Firewall.

        Args:
            **kwargs: Must contain:
                - ip (str): IP address to block
                - vsys (str, optional): Virtual system, defaults to vsys1
                - is_source_address (bool, optional): Block as source address

        Returns:
            Result with status and details
        """
        # Validate parameters
        ip = kwargs.get("ip", "").strip()
        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Sanitize IP
        ip = ip.replace(" ", "").strip("/").strip("-")
        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": ERR_INVALID_IP_FORMAT,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        vsys = kwargs.get("vsys", DEFAULT_VSYS)
        use_source = kwargs.get("is_source_address", DEFAULT_SOURCE_ADDRESS)

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Determine IP type
            ip_type = _find_ip_type(ip)
            if not ip_type:
                return {
                    "status": STATUS_ERROR,
                    "error": ERR_INVALID_IP_FORMAT,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # Create address object
            addr_name = _get_addr_name(ip, ip_type)

            # Add tag (using a simple tag)
            tag = "analysi-blocked"
            xpath = TAG_XPATH.format(vsys=vsys)
            element = f"<entry name='{tag}'><color>{TAG_COLOR}</color><comments>{TAG_CONTAINER_COMMENT}</comments></entry>"

            data = {
                "type": "config",
                "action": "set",
                "key": client.api_key,
                "xpath": xpath,
                "element": element,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Create address entry
            xpath = IP_ADDR_XPATH.format(vsys=vsys, ip_addr_name=addr_name)

            if ip_type == "ip-wildcard":
                element = f"<{ip_type}>{ip}</{ip_type}>"
            else:
                element = (
                    f"<{ip_type}>{ip}</{ip_type}><tag><member>{tag}</member></tag>"
                )

            data = {
                "type": "config",
                "action": "set",
                "key": client.api_key,
                "xpath": xpath,
                "element": element,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Determine address group name
            block_ip_grp = (
                BLOCK_IP_GROUP_NAME_SRC if use_source else BLOCK_IP_GROUP_NAME
            )

            # Add to address group (skip for wildcard IPs)
            if ip_type != "ip-wildcard":
                xpath = ADDR_GRP_XPATH.format(vsys=vsys, ip_group_name=block_ip_grp)
                element = f"<static><member>{addr_name}</member></static>"

                data = {
                    "type": "config",
                    "action": "set",
                    "key": client.api_key,
                    "xpath": xpath,
                    "element": element,
                }

                result = await client.make_rest_call(data)
                if result["status"] != STATUS_SUCCESS:
                    return result
            else:
                # For wildcard IPs, use address name directly
                block_ip_grp = addr_name

            # Create security policy
            result = await self._add_ip_security_policy(
                client, vsys, use_source, block_ip_grp
            )
            if result["status"] != STATUS_SUCCESS:
                return result

            # Commit configuration
            commit_result = await client.commit_config()
            if commit_result["status"] != STATUS_SUCCESS:
                return commit_result

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully blocked IP",
                "ip": ip,
                "vsys": vsys,
                "is_source_address": use_source,
            }

        except Exception as e:
            logger.error("Block IP failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Block IP failed: {e!s}",
                "error_type": type(e).__name__,
            }

    async def _add_ip_security_policy(
        self, client: PaloAltoAPIClient, vsys: str, use_source: bool, block_ip_grp: str
    ) -> dict[str, Any]:
        """Create IP security policy."""
        if use_source:
            sec_policy_name = SEC_POL_NAME_SRC.format(type=SEC_POL_IP_TYPE)
        else:
            sec_policy_name = SEC_POL_NAME.format(type=SEC_POL_IP_TYPE)

        # Build security policy element
        if use_source:
            element = "<from><member>any</member></from>"
            element += "<to><member>any</member></to>"
            element += f"<source><member>{block_ip_grp}</member></source>"
            element += "<destination><member>any</member></destination>"
        else:
            element = "<from><member>any</member></from>"
            element += "<to><member>any</member></to>"
            element += "<source><member>any</member></source>"
            element += f"<destination><member>{block_ip_grp}</member></destination>"

        element += "<source-user><member>any</member></source-user>"
        element += "<category><member>any</member></category>"
        element += "<service><member>application-default</member></service>"
        element += "<description>Created by Analysi, please don't edit</description>"

        # Add HIP profiles based on version
        if client.major_version and client.major_version > 9:
            element += "<source-hip><member>any</member></source-hip>"
            element += "<destination-hip><member>any</member></destination-hip>"
        else:
            element += "<hip-profiles><member>any</member></hip-profiles>"

        element += "<action>deny</action>"
        element += "<application><member>any</member></application>"

        xpath = SEC_POL_XPATH.format(vsys=vsys, sec_policy_name=sec_policy_name)
        data = {
            "type": "config",
            "action": "set",
            "key": client.api_key,
            "xpath": xpath,
            "element": element,
        }

        result = await client.make_rest_call(data)
        if result["status"] != STATUS_SUCCESS:
            return result

        # Move to top
        data = {
            "type": "config",
            "action": "move",
            "key": client.api_key,
            "xpath": xpath,
            "where": "top",
        }

        move_result = await client.make_rest_call(data)
        # Ignore "already at the top" errors
        if move_result["status"] != STATUS_SUCCESS:
            error_msg = move_result.get("error", "")
            if "already at the top" not in error_msg.lower():
                return move_result

        return {"status": STATUS_SUCCESS, "message": "Security policy created"}

class UnblockIpAction(IntegrationAction):
    """Unblock IP address by removing from address group."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock IP address in Palo Alto Networks Firewall.

        Args:
            **kwargs: Must contain:
                - ip (str): IP address to unblock
                - vsys (str, optional): Virtual system, defaults to vsys1
                - is_source_address (bool, optional): Unblock from source address list

        Returns:
            Result with status and details
        """
        # Validate parameters
        ip = kwargs.get("ip", "").strip()
        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Sanitize IP
        ip = ip.replace(" ", "").strip("/").strip("-")
        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": ERR_INVALID_IP_FORMAT,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        vsys = kwargs.get("vsys", DEFAULT_VSYS)
        use_source = kwargs.get("is_source_address", DEFAULT_SOURCE_ADDRESS)

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Determine IP type
            ip_type = _find_ip_type(ip)
            if not ip_type:
                return {
                    "status": STATUS_ERROR,
                    "error": ERR_INVALID_IP_FORMAT,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            addr_name = _get_addr_name(ip, ip_type)

            # Remove from address group or policy
            if ip_type == "ip-wildcard":
                # Remove from security policy directly
                if use_source:
                    sec_policy_name = SEC_POL_NAME_SRC.format(type=SEC_POL_IP_TYPE)
                    entry_type = "source"
                else:
                    sec_policy_name = SEC_POL_NAME.format(type=SEC_POL_IP_TYPE)
                    entry_type = "destination"

                xpath = SEC_POL_XPATH.format(vsys=vsys, sec_policy_name=sec_policy_name)
                xpath += f"/{entry_type}/member[text()='{addr_name}']"
            else:
                # Remove from address group
                block_ip_grp = (
                    BLOCK_IP_GROUP_NAME_SRC if use_source else BLOCK_IP_GROUP_NAME
                )
                xpath = ADDR_GRP_XPATH.format(vsys=vsys, ip_group_name=block_ip_grp)
                xpath += DEL_ADDR_GRP_XPATH.format(addr_name=addr_name)

            data = {
                "type": "config",
                "action": "delete",
                "key": client.api_key,
                "xpath": xpath,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            # Commit configuration
            commit_result = await client.commit_config()
            if commit_result["status"] != STATUS_SUCCESS:
                return commit_result

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully unblocked IP",
                "ip": ip,
                "vsys": vsys,
                "is_source_address": use_source,
            }

        except Exception as e:
            logger.error("Unblock IP failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Unblock IP failed: {e!s}",
                "error_type": type(e).__name__,
            }

class ListApplicationsAction(IntegrationAction):
    """List all applications available on the firewall."""

    async def execute(self, **kwargs) -> dict[str, Any]:  # noqa: C901
        """List applications in Palo Alto Networks Firewall.

        Args:
            **kwargs: May contain:
                - vsys (str, optional): Virtual system, defaults to vsys1

        Returns:
            Result with list of applications
        """
        vsys = kwargs.get("vsys", DEFAULT_VSYS)

        # Extract credentials
        device = self.settings.get(SETTINGS_DEVICE)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        verify = self.settings.get(SETTINGS_VERIFY_CERT, True)

        if not all([device, username, password]):
            return {
                "status": STATUS_ERROR,
                "error": ERR_MISSING_CREDENTIALS,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create client and authenticate
        client = PaloAltoAPIClient(
            device, username, password, verify, timeout, http_request=self.http_request
        )
        auth_result = await client.get_key()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            results = []

            # Get predefined applications
            data = {
                "type": "config",
                "action": "get",
                "key": client.api_key,
                "xpath": APP_LIST_XPATH,
            }

            result = await client.make_rest_call(data)
            if result["status"] != STATUS_SUCCESS:
                return result

            try:
                result_data = result.get("data", [])
                if result_data:
                    applications = result_data[0].get("application")
                    if applications:
                        entries = applications.get("entry", [])
                        if isinstance(entries, list):
                            results.extend(entries)
                        elif isinstance(entries, dict):
                            results.append(entries)
            except Exception as e:
                logger.error("Error parsing predefined applications", error=str(e))
                return {
                    "status": STATUS_ERROR,
                    "error": ERR_APP_RESPONSE,
                    "error_type": ERROR_TYPE_XML_PARSE,
                }

            # Get custom applications
            data["xpath"] = CUSTOM_APP_LIST_XPATH.format(vsys=vsys)

            result = await client.make_rest_call(data)
            # Custom apps may not exist - don't fail if not found
            if result["status"] == STATUS_SUCCESS:
                try:
                    result_data = result.get("data", [])
                    if result_data:
                        applications = result_data[0].get("application")
                        if applications:
                            entries = applications.get("entry", [])
                            if isinstance(entries, list):
                                results.extend(entries)
                            elif isinstance(entries, dict):
                                results.append(entries)
                except Exception as e:
                    logger.warning("Error parsing custom applications", error=str(e))

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully listed applications",
                "total_applications": len(results),
                "applications": results,
            }

        except Exception as e:
            logger.error("List applications failed", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"List applications failed: {e!s}",
                "error_type": type(e).__name__,
            }
