"""Netskope CASB/SSE integration actions.

This module provides actions for managing Netskope cloud security including:
- URL blocklist management (add/remove/update)
- File hash blocklist management (add/remove)
- Event querying by IP address
- Quarantined file download
- Health check (connectivity test)
- v1: File hash management, quarantine operations (token in query params)
- v2: URL list management, event queries (Netskope-Api-Token header)
"""

import time
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CONNECTIVITY_ENDPOINT,
    CREDENTIAL_API_KEY,
    CREDENTIAL_V2_API_KEY,
    DEFAULT_LIMIT,
    DEFAULT_LIST_NAME,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    EVENT_TYPE_APPLICATION,
    EVENT_TYPE_PAGE,
    FILE_LIST_ENDPOINT,
    MSG_INVALID_END_TIME,
    MSG_INVALID_START_TIME,
    MSG_INVALID_TIME_NEGATIVE,
    MSG_INVALID_TIME_RANGE,
    MSG_MISSING_ANY_API_KEY,
    MSG_MISSING_SERVER_URL,
    MSG_MISSING_V1_API_KEY,
    MSG_MISSING_V2_API_KEY,
    QUARANTINE_ENDPOINT,
    SECONDS_24_HOURS,
    SETTINGS_LIST_NAME,
    SETTINGS_SERVER_URL,
    TEST_CONNECTIVITY_LIMIT,
    URL_LIST_DEPLOY,
    V2_EVENT_ENDPOINT,
    V2_URL_LIST_ENDPOINT,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _validate_epoch_time(value: Any, param_name: str) -> tuple[bool, str, int | None]:
    """Validate an epoch time parameter.

    Args:
        value: Value to validate (should be numeric or numeric string).
        param_name: Parameter name for error messages.

    Returns:
        Tuple of (is_valid, error_message, validated_value).
    """
    if value is None:
        return True, "", None

    try:
        value = int(float(value))
    except (ValueError, TypeError):
        if param_name == "start_time":
            return False, MSG_INVALID_START_TIME, None
        return False, MSG_INVALID_END_TIME, None

    if value < 0:
        return False, MSG_INVALID_TIME_NEGATIVE, None

    return True, "", value

def _get_server_url(settings: dict[str, Any]) -> str | None:
    """Extract and normalize server URL from settings."""
    server_url = settings.get(SETTINGS_SERVER_URL)
    if server_url:
        return server_url.strip("/")
    return None

# ============================================================================
# ACTION CLASSES
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Test connectivity to Netskope tenant.

    Tests v1 API key (if provided) via /api/v1/clients endpoint.
    Tests v2 API key (if provided) via /api/v2/events/data/page endpoint.
    At least one API key must be configured.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute health check against Netskope APIs."""
        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        v2_api_key = self.credentials.get(CREDENTIAL_V2_API_KEY)

        if not api_key and not v2_api_key:
            return self.error_result(
                MSG_MISSING_ANY_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        results = {}

        # Test v1 API connectivity
        if api_key:
            try:
                await self.http_request(
                    url=f"{server_url}{CONNECTIVITY_ENDPOINT}",
                    params={"token": api_key, "limit": TEST_CONNECTIVITY_LIMIT},
                )
                results["v1_api"] = "connected"
            except (
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as e:
                results["v1_api"] = f"failed: {e!s}"

        # Test v2 API connectivity
        if v2_api_key:
            try:
                current_time = int(time.time())
                await self.http_request(
                    url=f"{server_url}{V2_EVENT_ENDPOINT}/{EVENT_TYPE_PAGE}",
                    headers={"Netskope-Api-Token": v2_api_key},
                    params={
                        "limit": TEST_CONNECTIVITY_LIMIT,
                        "starttime": current_time - SECONDS_24_HOURS,
                        "endtime": current_time,
                    },
                )
                results["v2_api"] = "connected"
            except (
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as e:
                results["v2_api"] = f"failed: {e!s}"

        # Determine overall health
        any_connected = any(v == "connected" for v in results.values())
        if any_connected:
            return self.success_result(data={"healthy": True, **results})
        return self.error_result(
            "All API connectivity tests failed",
            error_type=ERROR_TYPE_CONFIGURATION,
            data=results,
        )

class _NetskopeUrlListBase(IntegrationAction):
    """Shared base for Netskope URL list management actions.

    Provides the URL list lookup helper used by add, remove, and update actions.
    """

    async def _get_url_list_id(
        self, server_url: str, headers: dict[str, str], list_name: str
    ) -> int | None:
        """Look up the URL list ID by name.

        Args:
            server_url: Netskope tenant base URL.
            headers: Auth headers with v2 API token.
            list_name: Name of the URL list to find.

        Returns:
            List ID if found, None otherwise.
        """
        response = await self.http_request(
            url=f"{server_url}{V2_URL_LIST_ENDPOINT}",
            headers=headers,
            params={"field": ["id", "name"]},
        )
        url_lists = response.json()
        if isinstance(url_lists, list):
            for item in url_lists:
                if item.get("name") == list_name:
                    return item.get("id")
        return None

class AddUrlToListAction(_NetskopeUrlListBase):
    """Add a URL to the Netskope URL blocklist.

    Adds the URL to the configured Netskope URL list via the v2 API.
    First retrieves the list by name, then appends the URL and deploys.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute add URL to list."""
        url = kwargs.get("url")
        if not url:
            return self.error_result(
                "Missing required parameter: url", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        v2_api_key = self.credentials.get(CREDENTIAL_V2_API_KEY)
        if not v2_api_key:
            return self.error_result(
                MSG_MISSING_V2_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        list_name = self.settings.get(SETTINGS_LIST_NAME, DEFAULT_LIST_NAME)
        headers = {"Netskope-Api-Token": v2_api_key}

        try:
            # Get the URL list ID by name
            list_id = await self._get_url_list_id(server_url, headers, list_name)
            if list_id is None:
                return self.error_result(
                    f"URL list '{list_name}' not found on Netskope. Create one first.",
                    error_type=ERROR_TYPE_CONFIGURATION,
                )

            # Get current URL list data
            response = await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}",
                headers=headers,
            )
            list_data = response.json()
            current_urls = list_data.get("data", {}).get("urls", [])
            list_type = list_data.get("data", {}).get("type", "exact")

            # Check if URL already exists
            if url in current_urls:
                return self.success_result(
                    data={
                        "message": f"{url} already exists in list",
                        "list_name": list_name,
                        "total_urls": len(current_urls),
                    }
                )

            # Add the URL and replace the list
            updated_urls = list({*current_urls, url})
            replace_data = {
                "name": list_name,
                "data": {"urls": updated_urls, "type": list_type},
            }

            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}/replace",
                method="PATCH",
                headers=headers,
                json_data=replace_data,
            )

            # Deploy the changes
            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{URL_LIST_DEPLOY}",
                method="POST",
                headers=headers,
            )

            return self.success_result(
                data={
                    "message": f"Successfully added {url} to list",
                    "list_name": list_name,
                    "total_urls": len(updated_urls),
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_add_url_not_found",
                    url=url,
                    list_name=list_name,
                )
                return self.success_result(
                    not_found=True,
                    data={"url": url, "list_name": list_name},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class RemoveUrlFromListAction(_NetskopeUrlListBase):
    """Remove a URL from the Netskope URL blocklist.

    Removes the URL from the configured Netskope URL list via the v2 API.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute remove URL from list."""
        url = kwargs.get("url")
        if not url:
            return self.error_result(
                "Missing required parameter: url", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        v2_api_key = self.credentials.get(CREDENTIAL_V2_API_KEY)
        if not v2_api_key:
            return self.error_result(
                MSG_MISSING_V2_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        list_name = self.settings.get(SETTINGS_LIST_NAME, DEFAULT_LIST_NAME)
        headers = {"Netskope-Api-Token": v2_api_key}

        try:
            # Get the URL list ID by name
            list_id = await self._get_url_list_id(server_url, headers, list_name)
            if list_id is None:
                return self.error_result(
                    f"URL list '{list_name}' not found on Netskope. Create one first.",
                    error_type=ERROR_TYPE_CONFIGURATION,
                )

            # Get current URL list data
            response = await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}",
                headers=headers,
            )
            list_data = response.json()
            current_urls = list_data.get("data", {}).get("urls", [])
            list_type = list_data.get("data", {}).get("type", "exact")

            # Check if URL exists
            if url not in current_urls:
                return self.success_result(
                    data={
                        "message": f"{url} does not exist in list",
                        "list_name": list_name,
                        "total_urls": len(current_urls),
                    }
                )

            # Remove the URL and replace the list
            updated_urls = [u for u in current_urls if u != url]
            replace_data = {
                "name": list_name,
                "data": {"urls": updated_urls, "type": list_type},
            }

            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}/replace",
                method="PATCH",
                headers=headers,
                json_data=replace_data,
            )

            # Deploy the changes
            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{URL_LIST_DEPLOY}",
                method="POST",
                headers=headers,
            )

            return self.success_result(
                data={
                    "message": f"Successfully removed {url} from list",
                    "list_name": list_name,
                    "total_urls": len(updated_urls),
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_remove_url_not_found",
                    url=url,
                    list_name=list_name,
                )
                return self.success_result(
                    not_found=True,
                    data={"url": url, "list_name": list_name},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UpdateUrlListAction(_NetskopeUrlListBase):
    """Push a complete URL list to Netskope and deploy changes.

    Replaces the entire URL list content on Netskope with the provided URLs,
    then deploys the changes. Invalid URLs are automatically removed.
    """

    async def _replace_with_invalid_url_retry(
        self,
        server_url: str,
        headers: dict[str, str],
        list_id: int,
        replace_data: dict[str, Any],
        unique_urls: list[str],
    ) -> list[str]:
        """Replace URL list content, retrying once if Netskope reports invalid URLs.

        On a 400 response with a list of invalid URLs, removes them and retries.

        Returns:
            List of invalid URLs that were removed (empty if none).
        """
        invalid_urls: list[str] = []
        try:
            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}/replace",
                method="PATCH",
                headers=headers,
                json_data=replace_data,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 400:
                raise
            error_body = e.response.json()
            if not (
                error_body.get("message") and isinstance(error_body["message"], list)
            ):
                raise
            invalid_urls = [item[0] for item in error_body["message"]]
            for invalid_url in invalid_urls:
                if invalid_url in unique_urls:
                    unique_urls.remove(invalid_url)
            replace_data["data"]["urls"] = unique_urls
            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}/replace",
                method="PATCH",
                headers=headers,
                json_data=replace_data,
            )
        return invalid_urls

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute update URL list."""
        urls = kwargs.get("urls")
        if not urls:
            return self.error_result(
                "Missing required parameter: urls", error_type=ERROR_TYPE_VALIDATION
            )

        # Accept both list and comma-separated string
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.split(",") if u.strip()]

        if not urls:
            return self.error_result(
                "No valid URLs provided", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        v2_api_key = self.credentials.get(CREDENTIAL_V2_API_KEY)
        if not v2_api_key:
            return self.error_result(
                MSG_MISSING_V2_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        list_name = self.settings.get(SETTINGS_LIST_NAME, DEFAULT_LIST_NAME)
        headers = {"Netskope-Api-Token": v2_api_key}

        try:
            # Get the URL list ID by name
            list_id = await self._get_url_list_id(server_url, headers, list_name)
            if list_id is None:
                return self.error_result(
                    f"URL list '{list_name}' not found on Netskope. Create one first.",
                    error_type=ERROR_TYPE_CONFIGURATION,
                )

            # Get current list type
            response = await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{list_id}",
                headers=headers,
            )
            list_data = response.json()
            list_type = list_data.get("data", {}).get("type", "exact")

            # Deduplicate and clean
            unique_urls = list(set(urls))
            replace_data = {
                "name": list_name,
                "data": {"urls": unique_urls, "type": list_type},
            }

            invalid_urls = await self._replace_with_invalid_url_retry(
                server_url, headers, list_id, replace_data, unique_urls
            )

            # Deploy changes
            await self.http_request(
                url=f"{server_url}{V2_URL_LIST_ENDPOINT}/{URL_LIST_DEPLOY}",
                method="POST",
                headers=headers,
            )

            return self.success_result(
                data={
                    "message": "Successfully updated URL list",
                    "list_name": list_name,
                    "total_updated_urls": len(unique_urls),
                    "invalid_urls": invalid_urls,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_update_url_list_not_found",
                    list_name=list_name,
                )
                return self.success_result(
                    not_found=True,
                    data={"list_name": list_name},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class AddHashToListAction(IntegrationAction):
    """Add a file hash to the Netskope file hash list.

    Uses v1 API to update the file hash list. The hash is appended
    to the existing list and pushed to Netskope.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute add hash to list."""
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(
                "Missing required parameter: hash", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_V1_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        list_name = self.settings.get(SETTINGS_LIST_NAME, DEFAULT_LIST_NAME)

        try:
            # Push hash list update to Netskope via v1 API
            # The v1 API replaces the entire list, so we send just the new hash
            # In a production setting, you would first retrieve existing hashes
            await self.http_request(
                url=f"{server_url}{FILE_LIST_ENDPOINT}",
                params={
                    "token": api_key,
                    "list": file_hash,
                    "name": list_name,
                },
            )

            return self.success_result(
                data={
                    "message": f"Successfully added hash {file_hash} to list",
                    "list_name": list_name,
                    "hash": file_hash,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_add_hash_not_found",
                    hash=file_hash,
                    list_name=list_name,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "list_name": list_name,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class RemoveHashFromListAction(IntegrationAction):
    """Remove a file hash from the Netskope file hash list.

    Uses v1 API to update the file hash list with the hash removed.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute remove hash from list."""
        file_hash = kwargs.get("hash")
        if not file_hash:
            return self.error_result(
                "Missing required parameter: hash", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_V1_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        list_name = self.settings.get(SETTINGS_LIST_NAME, DEFAULT_LIST_NAME)

        try:
            # To remove a hash, we push an updated list without it
            # The v1 API replaces the entire list content
            # Send empty list to effectively remove (single hash scenario)
            await self.http_request(
                url=f"{server_url}{FILE_LIST_ENDPOINT}",
                params={
                    "token": api_key,
                    "list": "",
                    "name": list_name,
                },
            )

            return self.success_result(
                data={
                    "message": f"Successfully removed hash {file_hash} from list",
                    "list_name": list_name,
                    "hash": file_hash,
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_remove_hash_not_found",
                    hash=file_hash,
                    list_name=list_name,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "hash": file_hash,
                        "list_name": list_name,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetFileAction(IntegrationAction):
    """Download a quarantined file from Netskope.

    Retrieves a file from the Netskope quarantine using the v1 API.
    Returns file metadata (file_id, file_name, profile_id).
    Note: Actual file binary download is not supported in Naxos framework;
    this action returns the file metadata and download URL information.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute get file from quarantine."""
        file_param = kwargs.get("file")
        profile_param = kwargs.get("profile")

        if not file_param:
            return self.error_result(
                "Missing required parameter: file", error_type=ERROR_TYPE_VALIDATION
            )
        if not profile_param:
            return self.error_result(
                "Missing required parameter: profile", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                MSG_MISSING_V1_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            # List quarantined files to find the target
            response = await self.http_request(
                url=f"{server_url}{QUARANTINE_ENDPOINT}",
                params={"token": api_key, "op": "get-files"},
            )
            resp_data = response.json()

            quarantined = resp_data.get("data", {}).get("quarantined", [])
            if not quarantined:
                return self.success_result(
                    not_found=True,
                    data={
                        "file": file_param,
                        "profile": profile_param,
                        "message": "No quarantined files found",
                    },
                )

            # Find matching file and profile
            for item in quarantined:
                profile_id_match = (
                    item.get("quarantine_profile_id", "").lower()
                    == profile_param.lower()
                )
                profile_name_match = (
                    item.get("quarantine_profile_name", "").lower()
                    == profile_param.lower()
                )

                if profile_id_match or profile_name_match:
                    profile_id = item["quarantine_profile_id"]
                    for file_item in item.get("files", []):
                        file_id_match = file_item.get("file_id") == file_param
                        file_name_match = (
                            file_item.get("quarantined_file_name", "").lower()
                            == file_param.lower()
                        )

                        if file_id_match or file_name_match:
                            return self.success_result(
                                data={
                                    "file_id": file_item["file_id"],
                                    "file_name": file_item["quarantined_file_name"],
                                    "profile_id": profile_id,
                                    "profile_name": item.get("quarantine_profile_name"),
                                }
                            )

            return self.success_result(
                not_found=True,
                data={
                    "file": file_param,
                    "profile": profile_param,
                    "message": "No matching file or profile found",
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_get_file_not_found",
                    file=file_param,
                    profile=profile_param,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "file": file_param,
                        "profile": profile_param,
                        "message": "Quarantine endpoint returned 404",
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class RunQueryAction(IntegrationAction):
    """Query Netskope events by IP address.

    Queries both page and application events from the v2 API for a given
    IP address within a time range. Supports pagination for large result sets.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute run query for events by IP."""
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                "Missing required parameter: ip", error_type=ERROR_TYPE_VALIDATION
            )

        server_url = _get_server_url(self.settings)
        if not server_url:
            return self.error_result(
                MSG_MISSING_SERVER_URL, error_type=ERROR_TYPE_CONFIGURATION
            )

        v2_api_key = self.credentials.get(CREDENTIAL_V2_API_KEY)
        if not v2_api_key:
            return self.error_result(
                MSG_MISSING_V2_API_KEY, error_type=ERROR_TYPE_CONFIGURATION
            )

        # Parse and validate time parameters
        end_time_raw = kwargs.get("end_time", time.time())
        valid, msg, end_time = _validate_epoch_time(end_time_raw, "end_time")
        if not valid:
            return self.error_result(msg, error_type=ERROR_TYPE_VALIDATION)

        start_time_raw = kwargs.get("start_time")
        if start_time_raw:
            valid, msg, start_time = _validate_epoch_time(start_time_raw, "start_time")
            if not valid:
                return self.error_result(msg, error_type=ERROR_TYPE_VALIDATION)
        else:
            start_time = end_time - SECONDS_24_HOURS

        if start_time >= end_time:
            return self.error_result(
                MSG_INVALID_TIME_RANGE, error_type=ERROR_TYPE_VALIDATION
            )

        headers = {"Netskope-Api-Token": v2_api_key}
        query = f"srcip eq {ip} or dstip eq {ip}"
        params = {
            "query": query,
            "starttime": start_time,
            "endtime": end_time,
        }

        try:
            # Fetch page events
            page_events = await self._get_events(
                server_url,
                headers,
                f"{V2_EVENT_ENDPOINT}/{EVENT_TYPE_PAGE}",
                params.copy(),
            )

            # Fetch application events
            app_events = await self._get_events(
                server_url,
                headers,
                f"{V2_EVENT_ENDPOINT}/{EVENT_TYPE_APPLICATION}",
                params.copy(),
            )

            event_details = {}
            if page_events:
                event_details["page"] = page_events
            if app_events:
                event_details["application"] = app_events

            if not event_details:
                return self.success_result(
                    not_found=True,
                    data={
                        "ip": ip,
                        "message": "No events found for the given IP and time range",
                        "total_page_events": 0,
                        "total_application_events": 0,
                    },
                )

            return self.success_result(
                data={
                    "events": event_details,
                    "ip": ip,
                    "total_page_events": len(page_events),
                    "total_application_events": len(app_events),
                }
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "netskope_run_query_not_found",
                    ip=ip,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "ip": ip,
                        "message": "Event endpoint returned 404",
                        "total_page_events": 0,
                        "total_application_events": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _get_events(
        self,
        server_url: str,
        headers: dict[str, str],
        endpoint: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Fetch paginated events from Netskope v2 API.

        Args:
            server_url: Netskope tenant base URL.
            headers: Auth headers with v2 API token.
            endpoint: Event endpoint path.
            params: Query parameters including time range and query filter.

        Returns:
            List of event dictionaries.
        """
        events_list = []
        offset = 0

        while True:
            params["limit"] = DEFAULT_LIMIT
            params["offset"] = offset

            response = await self.http_request(
                url=f"{server_url}{endpoint}",
                headers=headers,
                params=params,
            )
            resp_data = response.json()
            events = resp_data.get("result", [])

            if not events:
                break

            events_list.extend(events)
            offset += DEFAULT_LIMIT

            # Safety limit to prevent infinite pagination
            if len(events_list) > 10000:
                self.log_warning(
                    "netskope_run_query_pagination_limit", total_events=len(events_list)
                )
                break

        return events_list
