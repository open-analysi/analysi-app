"""MISP (Malware Information Sharing Platform) integration actions.

Uses the MISP REST API directly (no PyMISP dependency).
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ANALYSIS_MAP,
    DISTRIBUTION_MAP,
    ENDPOINT_ATTRIBUTES,
    ENDPOINT_EVENTS,
    ENDPOINT_TAGS,
    ENDPOINT_VERSION,
    MSG_INVALID_ANALYSIS,
    MSG_INVALID_DISTRIBUTION,
    MSG_INVALID_EVENT_ID,
    MSG_INVALID_THREAT_LEVEL,
    MSG_MISSING_API_KEY,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_EVENT_ID,
    MSG_MISSING_INFO,
    THREAT_LEVEL_MAP,
)

logger = get_logger(__name__)

# ============================================================================
# HELPERS
# ============================================================================

def _get_base_url(settings: dict[str, Any]) -> str | None:
    """Extract and normalize base URL from settings."""
    base_url = settings.get("base_url")
    if base_url:
        return base_url.rstrip("/")
    return None

def _validate_event_id(event_id: Any) -> tuple[bool, str, int | None]:
    """Validate that event_id is a positive integer.

    Args:
        event_id: Raw event_id parameter value.

    Returns:
        Tuple of (is_valid, error_message, parsed_id).
    """
    if event_id is None:
        return False, MSG_MISSING_EVENT_ID, None
    try:
        parsed = int(event_id)
        if parsed <= 0:
            return False, MSG_INVALID_EVENT_ID, None
        return True, "", parsed
    except (TypeError, ValueError):
        return False, MSG_INVALID_EVENT_ID, None

def _resolve_enum_value(
    raw_value: str,
    lookup_map: dict[str, int],
    valid_range: range,
    error_message: str,
) -> tuple[int | None, str | None]:
    """Map a string or numeric value to an integer code via a lookup table.

    Args:
        raw_value: User-provided string (e.g. "High", "1").
        lookup_map: Case-insensitive name -> int mapping.
        valid_range: Allowed integer range for direct numeric input.
        error_message: Error to return on invalid input.

    Returns:
        Tuple of (resolved_int, error_message_or_None).
    """
    lower = str(raw_value).lower()
    resolved = lookup_map.get(lower)
    if resolved is not None:
        return resolved, None
    try:
        numeric = int(lower)
        if numeric not in valid_range:
            return None, error_message
        return numeric, None
    except (TypeError, ValueError):
        return None, error_message

# ============================================================================
# BASE CLASS
# ============================================================================

class _MISPBase(IntegrationAction):
    """Shared base for all MISP actions.

    Provides common HTTP headers (API key auth). The underscore prefix
    prevents the framework loader from treating this as a standalone action.
    """

    def get_http_headers(self) -> dict[str, str]:
        """Return MISP auth headers."""
        api_key = self.credentials.get("api_key", "")
        return {
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

# ============================================================================
# ACTIONS
# ============================================================================

class HealthCheckAction(_MISPBase):
    """Verify MISP API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check MISP API connectivity by requesting the server version.

        Returns:
            Success result with MISP version info, or error result.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_VERSION}",
            )
            version_info = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "version": version_info.get("version"),
                    "perm_sync": version_info.get("perm_sync"),
                },
            )
        except Exception as e:
            self.log_error("misp_health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})

class GetEventAction(_MISPBase):
    """Get event/incident details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve a MISP event by its ID.

        Args:
            **kwargs: Must contain 'event_id' (int or str).

        Returns:
            Success result with event data, or error result.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        is_valid, error_msg, event_id = _validate_event_id(kwargs.get("event_id"))
        if not is_valid:
            return self.error_result(error_msg, error_type="ValidationError")

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_EVENTS}/view/{event_id}",
            )
            event_data = response.json()
            return self.success_result(data=event_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("misp_event_not_found", event_id=event_id)
                return self.success_result(
                    not_found=True,
                    data={"event_id": event_id},
                )
            self.log_error("misp_get_event_failed", error=e, event_id=event_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("misp_get_event_failed", error=e, event_id=event_id)
            return self.error_result(e)

class SearchEventsAction(_MISPBase):
    """Search events by keyword, type, tags, or date range."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search MISP events using the restSearch API.

        Args:
            **kwargs: Optional filters:
                - value (str): Search value (IOC, keyword).
                - type (str): Attribute type filter (e.g. ip-src, domain).
                - tags (str): Comma-separated tags to filter by.
                - date_from (str): Start date (YYYY-MM-DD).
                - date_to (str): End date (YYYY-MM-DD).
                - limit (int): Max results (default 50).
                - event_id (str): Comma-separated event IDs.

        Returns:
            Success result with matching events.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        # Build search body
        search_body: dict[str, Any] = {
            "returnFormat": "json",
            "limit": kwargs.get("limit", 50),
        }

        if kwargs.get("value"):
            search_body["value"] = kwargs["value"]
        if kwargs.get("type"):
            search_body["type"] = kwargs["type"]
        if kwargs.get("tags"):
            search_body["tags"] = [
                t.strip() for t in kwargs["tags"].split(",") if t.strip()
            ]
        if kwargs.get("date_from"):
            search_body["from"] = kwargs["date_from"]
        if kwargs.get("date_to"):
            search_body["to"] = kwargs["date_to"]
        if kwargs.get("event_id"):
            raw_ids = kwargs["event_id"]
            if isinstance(raw_ids, str) and "," in raw_ids:
                search_body["eventid"] = [
                    eid.strip() for eid in raw_ids.split(",") if eid.strip()
                ]
            else:
                search_body["eventid"] = raw_ids

        try:
            response = await self.http_request(
                url=f"{base_url}/events/restSearch",
                method="POST",
                json_data=search_body,
            )
            result = response.json()

            # MISP returns {"response": [...]} for event searches
            events = (
                result.get("response", result) if isinstance(result, dict) else result
            )

            return self.success_result(
                data={
                    "events": events,
                    "count": len(events) if isinstance(events, list) else 0,
                }
            )

        except Exception as e:
            self.log_error("misp_search_events_failed", error=e)
            return self.error_result(e)

class CreateEventAction(_MISPBase):
    """Create a new event in MISP."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create a new MISP event.

        Args:
            **kwargs: Must contain:
                - info (str): Event description/title (required).
                - distribution (str): Sharing level (default: "This Community Only").
                - threat_level_id (str): Threat level (default: "Undefined").
                - analysis (str): Analysis status (default: "Initial").
                - tags (str, optional): Comma-separated tags.
                - published (bool, optional): Publish immediately (default: False).

        Returns:
            Success result with created event data.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        info = kwargs.get("info")
        if not info:
            return self.error_result(MSG_MISSING_INFO, error_type="ValidationError")

        # Map string values to MISP numeric codes
        distribution, err = _resolve_enum_value(
            kwargs.get("distribution", "This Community Only"),
            DISTRIBUTION_MAP,
            range(4),
            MSG_INVALID_DISTRIBUTION,
        )
        if err:
            return self.error_result(err, error_type="ValidationError")

        threat_level_id, err = _resolve_enum_value(
            kwargs.get("threat_level_id", "Undefined"),
            THREAT_LEVEL_MAP,
            range(1, 5),
            MSG_INVALID_THREAT_LEVEL,
        )
        if err:
            return self.error_result(err, error_type="ValidationError")

        analysis, err = _resolve_enum_value(
            kwargs.get("analysis", "Initial"),
            ANALYSIS_MAP,
            range(3),
            MSG_INVALID_ANALYSIS,
        )
        if err:
            return self.error_result(err, error_type="ValidationError")

        event_body = {
            "Event": {
                "info": info,
                "distribution": str(distribution),
                "threat_level_id": str(threat_level_id),
                "analysis": str(analysis),
                "published": kwargs.get("published", False),
            }
        }

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_EVENTS}/add",
                method="POST",
                json_data=event_body,
            )
            event_data = response.json()

            # Extract event ID for summary
            event = event_data.get("Event", event_data)
            created_event_id = event.get("id") if isinstance(event, dict) else None

            # Apply tags if provided
            tags = kwargs.get("tags", "")
            if tags and created_event_id:
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                for tag in tag_list:
                    try:
                        await self.http_request(
                            url=f"{base_url}/events/addTag/{created_event_id}/{tag}",
                            method="POST",
                            json_data={},
                        )
                    except Exception as tag_err:
                        self.log_warning(
                            "misp_tag_add_failed",
                            event_id=created_event_id,
                            tag=tag,
                            error=str(tag_err),
                        )

            return self.success_result(
                data=event_data,
                message=f"Event created with id: {created_event_id}",
            )

        except Exception as e:
            self.log_error("misp_create_event_failed", error=e)
            return self.error_result(e)

class AddAttributeAction(_MISPBase):
    """Add an attribute (IOC) to an existing event."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add an attribute to a MISP event.

        Args:
            **kwargs: Must contain:
                - event_id (int/str): Target event ID (required).
                - type (str): MISP attribute type (e.g. ip-src, domain, md5) (required).
                - value (str): Attribute value (required).
                - category (str, optional): Attribute category (e.g. Network activity).
                - to_ids (bool, optional): IDS flag (default: True).
                - comment (str, optional): Attribute comment.

        Returns:
            Success result with created attribute data.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        is_valid, error_msg, event_id = _validate_event_id(kwargs.get("event_id"))
        if not is_valid:
            return self.error_result(error_msg, error_type="ValidationError")

        attr_type = kwargs.get("type")
        if not attr_type:
            return self.error_result(
                "Missing required parameter: type", error_type="ValidationError"
            )

        attr_value = kwargs.get("value")
        if not attr_value:
            return self.error_result(
                "Missing required parameter: value", error_type="ValidationError"
            )

        attr_body: dict[str, Any] = {
            "event_id": event_id,
            "type": attr_type,
            "value": attr_value,
            "to_ids": kwargs.get("to_ids", True),
        }

        if kwargs.get("category"):
            attr_body["category"] = kwargs["category"]
        if kwargs.get("comment"):
            attr_body["comment"] = kwargs["comment"]

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_ATTRIBUTES}/add/{event_id}",
                method="POST",
                json_data=attr_body,
            )
            attr_data = response.json()

            return self.success_result(
                data=attr_data,
                message=f"Attribute added to event {event_id}",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("misp_event_not_found_for_attribute", event_id=event_id)
                return self.success_result(
                    not_found=True,
                    data={"event_id": event_id},
                )
            self.log_error("misp_add_attribute_failed", error=e, event_id=event_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("misp_add_attribute_failed", error=e, event_id=event_id)
            return self.error_result(e)

class SearchAttributesAction(_MISPBase):
    """Search attributes/IOCs across all events."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search MISP attributes using the restSearch API.

        Args:
            **kwargs: Optional filters:
                - value (str): Search for specific IOC value.
                - type (str): Attribute type filter (e.g. ip-src, domain).
                - tags (str): Comma-separated tags.
                - event_id (str): Comma-separated event IDs.
                - category (str): Attribute category.
                - limit (int): Max results (default 50).

        Returns:
            Success result with matching attributes.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        search_body: dict[str, Any] = {
            "returnFormat": "json",
            "limit": kwargs.get("limit", 50),
        }

        if kwargs.get("value"):
            search_body["value"] = kwargs["value"]
        if kwargs.get("type"):
            search_body["type"] = kwargs["type"]
        if kwargs.get("tags"):
            search_body["tags"] = [
                t.strip() for t in kwargs["tags"].split(",") if t.strip()
            ]
        if kwargs.get("event_id"):
            raw_ids = kwargs["event_id"]
            if isinstance(raw_ids, str) and "," in raw_ids:
                search_body["eventid"] = [
                    eid.strip() for eid in raw_ids.split(",") if eid.strip()
                ]
            else:
                search_body["eventid"] = raw_ids
        if kwargs.get("category"):
            search_body["category"] = kwargs["category"]

        try:
            response = await self.http_request(
                url=f"{base_url}/attributes/restSearch",
                method="POST",
                json_data=search_body,
            )
            result = response.json()

            # MISP returns {"response": {"Attribute": [...]}} for attribute searches
            attributes = []
            if isinstance(result, dict):
                resp = result.get("response", result)
                if isinstance(resp, dict):
                    attributes = resp.get("Attribute", [])
                elif isinstance(resp, list):
                    attributes = resp

            return self.success_result(
                data={"attributes": attributes, "count": len(attributes)},
            )

        except Exception as e:
            self.log_error("misp_search_attributes_failed", error=e)
            return self.error_result(e)

class GetAttributeAction(_MISPBase):
    """Get attribute details by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve a MISP attribute by its ID.

        Args:
            **kwargs: Must contain 'attribute_id' (int or str).

        Returns:
            Success result with attribute data, or error result.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        attribute_id = kwargs.get("attribute_id")
        if not attribute_id:
            return self.error_result(
                "Missing required parameter: attribute_id", error_type="ValidationError"
            )

        try:
            parsed_id = int(attribute_id)
            if parsed_id <= 0:
                return self.error_result(
                    "Parameter 'attribute_id' must be a positive integer",
                    error_type="ValidationError",
                )
        except (TypeError, ValueError):
            return self.error_result(
                "Parameter 'attribute_id' must be a positive integer",
                error_type="ValidationError",
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_ATTRIBUTES}/view/{parsed_id}",
            )
            attr_data = response.json()
            return self.success_result(data=attr_data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("misp_attribute_not_found", attribute_id=parsed_id)
                return self.success_result(
                    not_found=True,
                    data={"attribute_id": parsed_id},
                )
            self.log_error("misp_get_attribute_failed", error=e, attribute_id=parsed_id)
            return self.error_result(e)
        except Exception as e:
            self.log_error("misp_get_attribute_failed", error=e, attribute_id=parsed_id)
            return self.error_result(e)

class AddTagAction(_MISPBase):
    """Add a tag to an event or attribute."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a tag to a MISP event or attribute.

        Args:
            **kwargs: Must contain:
                - tag (str): Tag name to add (required).
                - event_id (int/str, optional): Event to tag.
                - attribute_id (int/str, optional): Attribute to tag.
                At least one of event_id or attribute_id must be provided.

        Returns:
            Success result with tag operation result.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        tag = kwargs.get("tag")
        if not tag:
            return self.error_result(
                "Missing required parameter: tag", error_type="ValidationError"
            )

        event_id = kwargs.get("event_id")
        attribute_id = kwargs.get("attribute_id")

        if not event_id and not attribute_id:
            return self.error_result(
                "At least one of event_id or attribute_id must be provided",
                error_type="ValidationError",
            )

        # Determine UUID-based tagging target
        # MISP /tags/attachTagToObject expects a UUID or numeric ID
        if event_id:
            target_type = "event"
            target_id = event_id
        else:
            target_type = "attribute"
            target_id = attribute_id

        try:
            response = await self.http_request(
                url=f"{base_url}/tags/attachTagToObject/{target_id}",
                method="POST",
                json_data={"tag": tag},
            )
            tag_data = response.json()

            return self.success_result(
                data=tag_data,
                message=f"Tag '{tag}' added to {target_type} {target_id}",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "misp_tag_target_not_found",
                    target_type=target_type,
                    target_id=target_id,
                )
                return self.success_result(
                    not_found=True,
                    data={f"{target_type}_id": target_id, "tag": tag},
                )
            self.log_error("misp_add_tag_failed", error=e)
            return self.error_result(e)
        except Exception as e:
            self.log_error("misp_add_tag_failed", error=e)
            return self.error_result(e)

class ListTagsAction(_MISPBase):
    """List available tags in the MISP instance."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all tags available in the MISP instance.

        Returns:
            Success result with list of tags.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        base_url = _get_base_url(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type="ConfigurationError"
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_TAGS}",
            )
            result = response.json()

            # MISP returns {"Tag": [...]}
            tags = result.get("Tag", result) if isinstance(result, dict) else result
            tag_list = tags if isinstance(tags, list) else []

            return self.success_result(
                data={"tags": tag_list, "count": len(tag_list)},
            )

        except Exception as e:
            self.log_error("misp_list_tags_failed", error=e)
            return self.error_result(e)
