"""
Vectra AI NDR integration actions.
Uses Token-based auth via Vectra REST API v2.5/v2.2.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.vectra.constants import (
    ADD_NOTE_ENDPOINT,
    ADD_REMOVE_TAGS_ENDPOINT,
    API_V2_2_VERSION,
    API_VERSION,
    ASSIGNMENTS_ENDPOINT,
    CREDENTIAL_API_TOKEN,
    DESCRIBE_DETECTION_ENDPOINT,
    DETECTIONS_ENDPOINT,
    ENTITY_ENDPOINT,
    ENTITY_TYPE_MAPPING,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_ENTITY_TYPE,
    MSG_INVALID_INTEGER,
    MSG_INVALID_OBJECT_TYPE,
    MSG_MISSING_API_TOKEN,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_PARAMETER,
    OUTCOMES_ENDPOINT,
    RESOLVE_ASSIGNMENT_ENDPOINT,
    SEARCH_DETECTIONS_ENDPOINT,
    SETTINGS_BASE_URL,
    TEST_CONNECTIVITY_ENDPOINT,
    VALID_ENTITIES,
    VALID_OBJECT_TYPES,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_integer(value: Any, name: str) -> int | None:
    """Validate that a value is a non-negative integer.

    Returns the integer on success, or None on failure.
    """
    try:
        if not float(value).is_integer():
            return None
        int_val = int(value)
        if int_val < 0:
            return None
        return int_val
    except (TypeError, ValueError):
        return None

def _parse_comma_list(raw: str) -> list[str]:
    """Parse a comma-separated string into a list of stripped, non-empty items."""
    return [item.strip() for item in raw.split(",") if item.strip()]

def _parse_int_list(raw: str) -> list[int]:
    """Parse a comma-separated string into a list of integer IDs."""
    return [int(item.strip()) for item in raw.split(",") if item.strip().isnumeric()]

class VectraBaseMixin:
    """Shared helpers for Vectra actions.

    Provides credential validation, base-URL resolution, and auth-header
    injection so every action class stays DRY.
    """

    def _get_base_url(self) -> str:
        """Return the Vectra Brain base URL (trailing slash stripped)."""
        return self.settings.get(SETTINGS_BASE_URL, "").rstrip("/")

    def get_http_headers(self) -> dict[str, str]:
        """Inject Token auth header into every request."""
        api_token = self.credentials.get(CREDENTIAL_API_TOKEN, "")
        headers: dict[str, str] = {}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"
        return headers

    def _validate_credentials(self) -> dict[str, Any] | None:
        """Return an error_result dict if credentials/settings are invalid, else None."""
        if not self.credentials.get(CREDENTIAL_API_TOKEN):
            return self.error_result(
                MSG_MISSING_API_TOKEN, error_type=ERROR_TYPE_CONFIGURATION
            )
        if not self._get_base_url():
            return self.error_result(
                MSG_MISSING_BASE_URL, error_type=ERROR_TYPE_CONFIGURATION
            )
        return None

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class HealthCheckAction(VectraBaseMixin, IntegrationAction):
    """Verify API connectivity to Vectra Brain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        base_url = self._get_base_url()
        url = f"{base_url}{API_VERSION}{TEST_CONNECTIVITY_ENDPOINT}"

        try:
            await self.http_request(url=url, params={"page_size": 1})
            return self.success_result(
                data={"message": "Test connectivity passed"},
                healthy=True,
            )
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc, data={"healthy": False})
        except Exception as exc:
            return self.error_result(exc, data={"healthy": False})

class GetEntityAction(VectraBaseMixin, IntegrationAction):
    """Get details of a host or account entity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        entity_type = kwargs.get("entity_type")
        entity_id_raw = kwargs.get("entity_id")

        if not entity_type:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_type"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if entity_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        entity_type = str(entity_type).lower()
        if entity_type not in VALID_ENTITIES:
            return self.error_result(
                MSG_INVALID_ENTITY_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        entity_id = _validate_integer(entity_id_raw, "entity_id")
        if entity_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self._get_base_url()
        endpoint = ENTITY_ENDPOINT.format(
            entity_type=ENTITY_TYPE_MAPPING[entity_type],
            entity_id=entity_id,
        )
        url = f"{base_url}{API_VERSION}{endpoint}"

        try:
            response = await self.http_request(url=url)
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                self.log_info(
                    "vectra_get_entity_not_found",
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"entity_type": entity_type, "entity_id": entity_id},
                )
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class ListDetectionsAction(VectraBaseMixin, IntegrationAction):
    """List detections for an entity with optional filters."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        entity_type = kwargs.get("entity_type")
        entity_id_raw = kwargs.get("entity_id")

        if not entity_type:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_type"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if entity_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        entity_type = str(entity_type).lower()
        if entity_type not in VALID_ENTITIES:
            return self.error_result(
                MSG_INVALID_ENTITY_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        entity_id = _validate_integer(entity_id_raw, "entity_id")
        if entity_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Match upstream: for accounts use "linked_account" in search query
        search_entity = "linked_account" if entity_type == "account" else entity_type
        query = (
            f'detection.src_{search_entity}.id:{entity_id} AND detection.state:"active"'
        )

        base_url = self._get_base_url()
        url = f"{base_url}{API_V2_2_VERSION}{SEARCH_DETECTIONS_ENDPOINT}"

        try:
            all_results: list[dict] = []
            next_page_url: str | None = None

            while True:
                request_url = next_page_url or url
                params = {"query_string": query} if not next_page_url else {}

                response = await self.http_request(url=request_url, params=params)
                data = response.json()

                results = data.get("results", [])
                all_results.extend(results)

                next_link = data.get("next")
                if next_link:
                    next_page_url = next_link
                else:
                    break

            return self.success_result(
                data={
                    "detections": all_results,
                    "total_detections": len(all_results),
                },
            )
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class GetDetectionAction(VectraBaseMixin, IntegrationAction):
    """Get detection details by detection ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        detection_id_raw = kwargs.get("detection_id")
        if detection_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("detection_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        detection_id = _validate_integer(detection_id_raw, "detection_id")
        if detection_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("detection_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self._get_base_url()
        endpoint = DESCRIBE_DETECTION_ENDPOINT.format(detection_id=detection_id)
        url = f"{base_url}{API_VERSION}{endpoint}"

        try:
            response = await self.http_request(url=url)
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                self.log_info(
                    "vectra_get_detection_not_found", detection_id=detection_id
                )
                return self.success_result(
                    not_found=True,
                    data={"detection_id": detection_id},
                )
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class MarkDetectionAction(VectraBaseMixin, IntegrationAction):
    """Mark a detection as fixed."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        detection_id_raw = kwargs.get("detection_id")
        if detection_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("detection_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        detection_id = _validate_integer(detection_id_raw, "detection_id")
        if detection_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("detection_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self._get_base_url()
        url = f"{base_url}{API_VERSION}{DETECTIONS_ENDPOINT}"
        payload = {"detectionIdList": [detection_id], "mark_as_fixed": "True"}

        try:
            response = await self.http_request(
                url=url, method="PATCH", json_data=payload
            )
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class UnmarkDetectionAction(VectraBaseMixin, IntegrationAction):
    """Unmark a detection (remove fixed status)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        detection_id_raw = kwargs.get("detection_id")
        if detection_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("detection_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        detection_id = _validate_integer(detection_id_raw, "detection_id")
        if detection_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("detection_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self._get_base_url()
        url = f"{base_url}{API_VERSION}{DETECTIONS_ENDPOINT}"
        payload = {"detectionIdList": [detection_id], "mark_as_fixed": "False"}

        try:
            response = await self.http_request(
                url=url, method="PATCH", json_data=payload
            )
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class AddNoteAction(VectraBaseMixin, IntegrationAction):
    """Add a note to an entity or detection."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        object_type = kwargs.get("object_type")
        object_id_raw = kwargs.get("object_id")
        note = kwargs.get("note")

        if not object_type:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("object_type"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if object_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("object_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not note:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("note"), error_type=ERROR_TYPE_VALIDATION
            )

        object_type = str(object_type).lower()
        if object_type not in VALID_OBJECT_TYPES:
            return self.error_result(
                MSG_INVALID_OBJECT_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        object_id = _validate_integer(object_id_raw, "object_id")
        if object_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("object_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self._get_base_url()
        endpoint = ADD_NOTE_ENDPOINT.format(
            object_type=ENTITY_TYPE_MAPPING[object_type],
            object_id=object_id,
        )
        url = f"{base_url}{API_VERSION}{endpoint}"

        try:
            response = await self.http_request(
                url=url, method="POST", json_data={"note": note}
            )
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class ListAssignmentsAction(VectraBaseMixin, IntegrationAction):
    """List analyst assignments."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        base_url = self._get_base_url()
        url = f"{base_url}{API_VERSION}{ASSIGNMENTS_ENDPOINT}"

        try:
            all_results: list[dict] = []
            next_page_url: str | None = None

            while True:
                request_url = next_page_url or url

                response = await self.http_request(url=request_url)
                data = response.json()

                results = data.get("results", [])
                all_results.extend(results)

                next_link = data.get("next")
                if next_link:
                    next_page_url = next_link
                else:
                    break

            return self.success_result(
                data={
                    "assignments": all_results,
                    "total_assignments": len(all_results),
                },
            )
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class ResolveAssignmentAction(VectraBaseMixin, IntegrationAction):
    """Resolve an analyst assignment with outcome and optional note."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        assignment_id_raw = kwargs.get("assignment_id")
        outcome_title = kwargs.get("outcome")

        if assignment_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("assignment_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not outcome_title:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("outcome"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        assignment_id = _validate_integer(assignment_id_raw, "assignment_id")
        if assignment_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("assignment_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Resolve outcome title to outcome ID via the outcomes endpoint
        base_url = self._get_base_url()
        outcome_id = await self._resolve_outcome(base_url, outcome_title)
        if outcome_id is None:
            return self.error_result(
                f"Invalid outcome: '{outcome_title}'. Could not resolve to a valid outcome ID.",
                error_type=ERROR_TYPE_VALIDATION,
            )

        note = kwargs.get("note", "Resolved via Analysi")
        triage_as = kwargs.get("triage_as")
        detection_ids_raw = kwargs.get("detection_ids", "")
        detection_ids = _parse_int_list(detection_ids_raw) if detection_ids_raw else []

        endpoint = RESOLVE_ASSIGNMENT_ENDPOINT.format(assignment_id=assignment_id)
        url = f"{base_url}{API_VERSION}{endpoint}"
        payload: dict[str, Any] = {
            "outcome": outcome_id,
            "note": note,
            "detection_ids": detection_ids,
        }
        if triage_as:
            payload["triage_as"] = triage_as

        try:
            response = await self.http_request(url=url, method="PUT", json_data=payload)
            resp_data = response.json()
            return self.success_result(data=resp_data.get("assignment", resp_data))
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

    async def _resolve_outcome(self, base_url: str, outcome_title: str) -> str | None:
        """Map an outcome title to its numeric ID via the outcomes API."""
        url = f"{base_url}{API_VERSION}{OUTCOMES_ENDPOINT}"
        try:
            all_outcomes: list[dict] = []
            next_page_url: str | None = None

            while True:
                request_url = next_page_url or url
                response = await self.http_request(url=request_url)
                data = response.json()

                results = data.get("results", [])
                all_outcomes.extend(results)

                next_link = data.get("next")
                if next_link:
                    next_page_url = next_link
                else:
                    break

            for item in all_outcomes:
                if item.get("title") == outcome_title:
                    return str(item.get("id"))

            return None
        except Exception:
            return None

class AddTagsAction(VectraBaseMixin, IntegrationAction):
    """Add tags to an entity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        entity_type = kwargs.get("entity_type")
        entity_id_raw = kwargs.get("entity_id")
        tags_raw = kwargs.get("tags")

        if not entity_type:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_type"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if entity_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not tags_raw:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("tags"), error_type=ERROR_TYPE_VALIDATION
            )

        entity_type = str(entity_type).lower()
        if entity_type not in VALID_ENTITIES:
            return self.error_result(
                MSG_INVALID_ENTITY_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        entity_id = _validate_integer(entity_id_raw, "entity_id")
        if entity_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        new_tags = _parse_comma_list(str(tags_raw))
        if not new_tags:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("tags"), error_type=ERROR_TYPE_VALIDATION
            )

        base_url = self._get_base_url()
        tag_endpoint = ADD_REMOVE_TAGS_ENDPOINT.format(
            entity_type=entity_type, entity_id=entity_id
        )
        tag_url = f"{base_url}{API_VERSION}{tag_endpoint}"

        try:
            # Fetch existing tags
            get_response = await self.http_request(url=tag_url)
            existing_tags = get_response.json().get("tags", [])

            # Merge and deduplicate (preserve order)
            merged = list(dict.fromkeys(existing_tags + new_tags))

            # Update tags
            response = await self.http_request(
                url=tag_url, method="PATCH", json_data={"tags": merged}
            )
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)

class RemoveTagsAction(VectraBaseMixin, IntegrationAction):
    """Remove tags from an entity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        err = self._validate_credentials()
        if err:
            return err

        entity_type = kwargs.get("entity_type")
        entity_id_raw = kwargs.get("entity_id")
        tags_raw = kwargs.get("tags")

        if not entity_type:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_type"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if entity_id_raw is None:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not tags_raw:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("tags"), error_type=ERROR_TYPE_VALIDATION
            )

        entity_type = str(entity_type).lower()
        if entity_type not in VALID_ENTITIES:
            return self.error_result(
                MSG_INVALID_ENTITY_TYPE, error_type=ERROR_TYPE_VALIDATION
            )

        entity_id = _validate_integer(entity_id_raw, "entity_id")
        if entity_id is None:
            return self.error_result(
                MSG_INVALID_INTEGER.format("entity_id"),
                error_type=ERROR_TYPE_VALIDATION,
            )

        remove_tags = _parse_comma_list(str(tags_raw))
        if not remove_tags:
            return self.error_result(
                MSG_MISSING_PARAMETER.format("tags"), error_type=ERROR_TYPE_VALIDATION
            )

        base_url = self._get_base_url()
        tag_endpoint = ADD_REMOVE_TAGS_ENDPOINT.format(
            entity_type=entity_type, entity_id=entity_id
        )
        tag_url = f"{base_url}{API_VERSION}{tag_endpoint}"

        try:
            # Fetch existing tags
            get_response = await self.http_request(url=tag_url)
            existing_tags = get_response.json().get("tags", [])

            # Remove specified tags
            remaining = [t for t in existing_tags if t not in remove_tags]

            # Update tags
            response = await self.http_request(
                url=tag_url, method="PATCH", json_data={"tags": remaining}
            )
            return self.success_result(data=response.json())
        except httpx.HTTPStatusError as exc:
            return self.error_result(exc)
        except Exception as exc:
            return self.error_result(exc)
