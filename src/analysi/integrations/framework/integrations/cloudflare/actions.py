"""Cloudflare WAF/CDN integration actions.

This module provides actions for managing Cloudflare Firewall including:
- Health check (test connectivity by listing zones)
- Block IP (create firewall filter + rule to block an IP)
- Block user agent (create firewall filter + rule to block a user agent)
- Update rule (enable or disable a firewall rule by name)

Cloudflare uses Bearer token authentication via API tokens.
Auth is injected into every request through ``get_http_headers()``.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_API_TOKEN,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    DUPLICATE_ERROR_CODE,
    ENDPOINT_FILTERS,
    ENDPOINT_FIREWALL_RULES,
    ENDPOINT_ZONES,
    ERR_INVALID_ACTION,
    ERR_MISSING_API_TOKEN,
    ERR_MISSING_PARAM,
    ERR_PARSE_RESPONSE,
    ERR_RULE_NOT_FOUND,
    ERR_ZONE_NOT_FOUND,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    FILTER_EXPR_IP,
    FILTER_EXPR_USER_AGENT,
    MSG_HEALTH_CHECK_PASSED,
    MSG_IP_BLOCK_RULE_UPDATED,
    MSG_IP_BLOCKED,
    MSG_RULE_UPDATED,
    MSG_USER_AGENT_BLOCK_RULE_UPDATED,
    MSG_USER_AGENT_BLOCKED,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    VALID_RULE_ACTIONS,
)

logger = get_logger(__name__)

# ============================================================================
# BASE CLASS
# ============================================================================

class _CloudflareBase(IntegrationAction):
    """Shared base for all Cloudflare actions.

    Provides Bearer token auth, configurable base URL, and timeout.
    """

    def get_http_headers(self) -> dict[str, str]:
        """Return Bearer token auth header plus JSON content type."""
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN, "")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        return headers

    def get_timeout(self) -> int | float:
        """Return configured timeout."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    def _get_base_url(self) -> str:
        """Return the Cloudflare API base URL (no trailing slash)."""
        url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        return url.rstrip("/")

    def _validate_api_token(self) -> dict[str, Any] | None:
        """Validate that api_token is present. Return error dict or None."""
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN)
        if not api_token:
            return self.error_result(
                ERR_MISSING_API_TOKEN,
                error_type=ERROR_TYPE_CONFIGURATION,
            )
        return None

    async def _get_zone_id(self, domain_name: str) -> str:
        """Look up a Cloudflare zone ID by domain name.

        Raises ValueError if no zone is found for the given domain.
        """
        base_url = self._get_base_url()
        response = await self.http_request(
            url=f"{base_url}{ENDPOINT_ZONES}",
            params={"name": domain_name},
        )
        resp_json = response.json()
        results = resp_json.get("result", [])
        if not results:
            raise ValueError(ERR_ZONE_NOT_FOUND.format(domain=domain_name))
        return results[0]["id"]

    async def _create_filter(
        self,
        zone_id: str,
        expression: str,
    ) -> str:
        """Create a Cloudflare filter and return the filter ID.

        If the filter already exists (duplicate error 10102), extracts
        and returns the existing filter ID from the error metadata.
        """
        base_url = self._get_base_url()
        payload = [{"expression": expression}]

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_FILTERS.format(zone_id=zone_id)}",
                method="POST",
                json_data=payload,
            )
            resp_json = response.json()
            return resp_json["result"][0]["id"]

        except httpx.HTTPStatusError as e:
            # Check if this is a duplicate filter error
            try:
                err_body = e.response.json()
                errors = err_body.get("errors", [])
                if errors and errors[0].get("code") == DUPLICATE_ERROR_CODE:
                    return errors[0]["meta"]["id"]
            except Exception:
                pass
            raise

    async def _create_firewall_rule(
        self,
        zone_id: str,
        filter_id: str,
        description: str,
    ) -> dict[str, Any]:
        """Create a firewall rule using the given filter ID.

        If the rule already exists (duplicate error 10102), updates
        the existing rule instead.

        Returns a dict with 'rule_id' and 'created' (bool).
        """
        base_url = self._get_base_url()
        payload = {
            "filter": {"id": filter_id},
            "action": "block",
            "description": description,
            "paused": False,
        }

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_FIREWALL_RULES.format(zone_id=zone_id)}",
                method="POST",
                json_data=[payload],
            )
            resp_json = response.json()
            rule_id = resp_json["result"][0]["id"]
            return {"rule_id": rule_id, "created": True}

        except httpx.HTTPStatusError as e:
            # Check if this is a duplicate rule error
            try:
                err_body = e.response.json()
                errors = err_body.get("errors", [])
                if errors and errors[0].get("code") == DUPLICATE_ERROR_CODE:
                    rule_id = errors[0]["meta"]["id"]
                    # Update existing rule
                    payload["id"] = rule_id
                    await self.http_request(
                        url=f"{base_url}{ENDPOINT_FIREWALL_RULES.format(zone_id=zone_id)}",
                        method="PUT",
                        json_data=[payload],
                    )
                    return {"rule_id": rule_id, "created": False}
            except httpx.HTTPStatusError:
                raise
            except Exception:
                pass
            raise

# ============================================================================
# ACTION CLASSES
# ============================================================================

class HealthCheckAction(_CloudflareBase):
    """Test connectivity to the Cloudflare API.

    Validates credentials by listing zones. Matches the upstream test_connectivity.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to Cloudflare."""
        err = self._validate_api_token()
        if err:
            return err

        try:
            response = await self.http_request(
                url=f"{self._get_base_url()}{ENDPOINT_ZONES}",
            )

            resp_json = response.json()
            if not resp_json.get("success", False):
                return self.error_result(
                    ERR_PARSE_RESPONSE,
                    error_type=ERROR_TYPE_CONFIGURATION,
                )

            return self.success_result(
                data={"message": MSG_HEALTH_CHECK_PASSED, "healthy": True},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return self.error_result(
                    "Authentication failed. Check API token.",
                    error_type=ERROR_TYPE_AUTHENTICATION,
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockIpAction(_CloudflareBase):
    """Block an IP address via Cloudflare firewall rules.

    This action:
    1. Resolves the zone ID from the domain name.
    2. Creates a filter expression matching the source IP.
    3. Creates a firewall rule using that filter (or updates if it exists).
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block an IP address on Cloudflare."""
        err = self._validate_api_token()
        if err:
            return err

        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="ip"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        domain_name = kwargs.get("domain_name")
        if not domain_name:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="domain_name"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        rule_description = kwargs.get("rule_description", "Analysi Block IP")

        try:
            # Step 1: Get zone ID
            zone_id = await self._get_zone_id(domain_name)

            # Step 2: Create filter for IP
            expression = FILTER_EXPR_IP.format(ip=ip)
            filter_id = await self._create_filter(zone_id, expression)

            # Step 3: Create firewall rule
            rule_result = await self._create_firewall_rule(
                zone_id, filter_id, rule_description
            )

            message = (
                MSG_IP_BLOCKED if rule_result["created"] else MSG_IP_BLOCK_RULE_UPDATED
            )
            return self.success_result(
                data={
                    "message": message,
                    "ip": ip,
                    "domain_name": domain_name,
                    "zone_id": zone_id,
                    "filter_id": filter_id,
                    "rule_id": rule_result["rule_id"],
                },
            )

        except ValueError as e:
            # Zone not found
            return self.error_result(str(e), error_type=ERROR_TYPE_VALIDATION)
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockUserAgentAction(_CloudflareBase):
    """Block a user agent via Cloudflare firewall rules.

    This action:
    1. Resolves the zone ID from the domain name.
    2. Creates a filter expression matching the user agent string.
    3. Creates a firewall rule using that filter (or updates if it exists).
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block a user agent on Cloudflare."""
        err = self._validate_api_token()
        if err:
            return err

        user_agent = kwargs.get("user_agent")
        if not user_agent:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="user_agent"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        domain_name = kwargs.get("domain_name")
        if not domain_name:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="domain_name"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        rule_description = kwargs.get("rule_description", "Analysi Block UserAgent")

        try:
            # Step 1: Get zone ID
            zone_id = await self._get_zone_id(domain_name)

            # Step 2: Create filter for user agent
            expression = FILTER_EXPR_USER_AGENT.format(ua=user_agent)
            filter_id = await self._create_filter(zone_id, expression)

            # Step 3: Create firewall rule
            rule_result = await self._create_firewall_rule(
                zone_id, filter_id, rule_description
            )

            message = (
                MSG_USER_AGENT_BLOCKED
                if rule_result["created"]
                else MSG_USER_AGENT_BLOCK_RULE_UPDATED
            )
            return self.success_result(
                data={
                    "message": message,
                    "user_agent": user_agent,
                    "domain_name": domain_name,
                    "zone_id": zone_id,
                    "filter_id": filter_id,
                    "rule_id": rule_result["rule_id"],
                },
            )

        except ValueError as e:
            return self.error_result(str(e), error_type=ERROR_TYPE_VALIDATION)
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UpdateRuleAction(_CloudflareBase):
    """Enable or disable a Cloudflare firewall rule by name.

    Looks up the rule by description within a zone, then sets its
    ``paused`` field based on the requested action (block/allow).
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update a firewall rule on Cloudflare."""
        err = self._validate_api_token()
        if err:
            return err

        rule_name = kwargs.get("rule_name")
        if not rule_name:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="rule_name"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        domain_name = kwargs.get("domain_name")
        if not domain_name:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="domain_name"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        action = kwargs.get("action")
        if not action:
            return self.error_result(
                ERR_MISSING_PARAM.format(param="action"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        if action not in VALID_RULE_ACTIONS:
            return self.error_result(
                ERR_INVALID_ACTION.format(action=action),
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            base_url = self._get_base_url()

            # Step 1: Get zone ID
            zone_id = await self._get_zone_id(domain_name)

            # Step 2: Find firewall rule by description
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_FIREWALL_RULES.format(zone_id=zone_id)}",
                params={"description": rule_name},
            )
            resp_json = response.json()
            rules = resp_json.get("result", [])

            if not rules:
                return self.error_result(
                    ERR_RULE_NOT_FOUND.format(rule_name=rule_name),
                    error_type=ERROR_TYPE_VALIDATION,
                )

            # Use the first matching rule (upstream assumes unique)
            rule_payload = rules[0]
            rule_payload["paused"] = VALID_RULE_ACTIONS[action]

            # Step 3: Update the rule
            await self.http_request(
                url=f"{base_url}{ENDPOINT_FIREWALL_RULES.format(zone_id=zone_id)}",
                method="PUT",
                json_data=[rule_payload],
            )

            return self.success_result(
                data={
                    "message": MSG_RULE_UPDATED,
                    "rule_name": rule_name,
                    "rule_id": rule_payload.get("id"),
                    "domain_name": domain_name,
                    "action": action,
                    "paused": rule_payload["paused"],
                },
            )

        except ValueError as e:
            return self.error_result(str(e), error_type=ERROR_TYPE_VALIDATION)
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
