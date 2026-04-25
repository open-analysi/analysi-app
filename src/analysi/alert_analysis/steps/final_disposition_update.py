"""Step 5: Final Disposition Update Implementation"""

import re
from typing import Any

from analysi.alert_analysis.clients import BackendAPIClient
from analysi.common.internal_auth import internal_auth_headers
from analysi.common.internal_client import InternalAsyncClient
from analysi.config.logging import get_logger

logger = get_logger(__name__)


class FinalDispositionUpdateStep:
    """
    Final disposition update step that:
    1. Retrieves artifacts from workflow execution
    2. Fetches available dispositions from database
    3. Matches disposition text to a real disposition
    4. Updates the alert_analysis record with results
    """

    def __init__(self, tenant_id: str = "default"):
        self.api_client = BackendAPIClient()
        self.tenant_id = tenant_id

    async def execute(
        self,
        tenant_id: str,
        alert_id: str,
        analysis_id: str,
        workflow_run_id: str,
        workflow_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Match disposition and update analysis with workflow results.

        Returns:
            Dict with disposition results
        """
        logger.info(
            "starting_final_disposition_update_for_analysis", analysis_id=analysis_id
        )

        try:
            # Get artifacts from workflow run
            artifacts = await self._get_workflow_artifacts(tenant_id, workflow_run_id)

            # Extract relevant artifact contents
            disposition_text = await self._extract_artifact_content(
                artifacts, "Disposition", tenant_id
            )
            short_summary = await self._extract_artifact_content(
                artifacts, "Alert Summary", tenant_id
            )
            long_summary = await self._extract_artifact_content(
                artifacts, "Detailed Analysis", tenant_id
            )

            # Get available dispositions from database
            dispositions = await self.api_client.get_dispositions(tenant_id)

            # Extract confidence: prefer Disposition text, fall back to Detailed Analysis
            confidence = self._extract_confidence(disposition_text)
            if confidence == 75 and long_summary:
                # 75 is the default — Disposition text had no explicit confidence.
                # Check Detailed Analysis where it usually appears
                # (e.g., "High (80% confidence)")
                analysis_confidence = self._extract_confidence(long_summary)
                if analysis_confidence != 75:
                    confidence = analysis_confidence

            # Match disposition text to actual disposition.
            # If no Disposition artifact exists (e.g., HITL workflow where
            # the upstream disposition task had no detailed analysis input),
            # complete the analysis without a disposition rather than
            # crashing and discarding all prior workflow output.
            try:
                matched_disposition = await self._match_disposition(
                    disposition_text, dispositions, confidence=confidence
                )
            except ValueError as e:
                logger.warning(
                    "disposition_matching_failed_using_fallback",
                    analysis_id=analysis_id,
                    error=str(e),
                )
                # Fall back to "Insufficient Data" disposition so the alert
                # has a real disposition rather than showing blank.
                fallback = self._find_fallback_disposition(dispositions)
                await self._complete_analysis(
                    tenant_id=tenant_id,
                    analysis_id=analysis_id,
                    disposition_id=fallback["id"] if fallback else None,
                    confidence=fallback["confidence"] if fallback else 0,
                    short_summary=short_summary,
                    long_summary=long_summary,
                    workflow_id=workflow_id,
                    workflow_run_id=workflow_run_id,
                    disposition_category=fallback.get("category") if fallback else None,
                    disposition_subcategory=fallback.get("subcategory")
                    if fallback
                    else None,
                    disposition_display_name=fallback["name"] if fallback else None,
                    disposition_confidence=fallback["confidence"] if fallback else 0,
                )
                return {
                    "disposition_id": fallback["id"] if fallback else None,
                    "disposition_name": fallback["name"] if fallback else None,
                    "confidence": fallback["confidence"] if fallback else 0,
                    "short_summary": (short_summary[:100] if short_summary else None),
                    "status": "completed",
                    "warning": str(e),
                }

            # Update alert_analysis record and alert status
            await self._complete_analysis(
                tenant_id=tenant_id,
                analysis_id=analysis_id,
                disposition_id=matched_disposition["id"],
                confidence=matched_disposition["confidence"],
                short_summary=short_summary,
                long_summary=long_summary,
                workflow_id=workflow_id,
                workflow_run_id=workflow_run_id,
                disposition_category=matched_disposition.get("category"),
                disposition_subcategory=matched_disposition.get("subcategory"),
                disposition_display_name=matched_disposition["name"],
                disposition_confidence=matched_disposition["confidence"],
            )

            result = {
                "disposition_id": matched_disposition["id"],
                "disposition_name": matched_disposition["name"],
                "confidence": matched_disposition["confidence"],
                "short_summary": (
                    short_summary[:100] if short_summary else None
                ),  # Truncate for logging
                "status": "completed",
            }

            logger.info(
                "disposition_matched",
                disposition_name=result["disposition_name"],
                confidence=result["confidence"],
            )
            return result

        except Exception as e:
            logger.error("failed_to_update_disposition", error=str(e))
            raise

    async def _get_workflow_artifacts(
        self, tenant_id: str, workflow_run_id: str
    ) -> list[dict[str, Any]]:
        """
        Retrieve artifacts from workflow run.
        """
        try:
            artifacts = await self.api_client.get_artifacts_by_workflow_run(
                tenant_id, workflow_run_id
            )
            logger.info(
                "retrieved_artifacts_from_workflow", artifacts_count=len(artifacts)
            )
            return artifacts
        except Exception as e:
            logger.warning(
                "failed_to_retrieve_artifacts_using_default_values", error=str(e)
            )
            # Return empty list if artifacts can't be retrieved
            return []

    async def _fetch_artifact_content(
        self, tenant_id: str, artifact_id: str
    ) -> str | None:
        """
        Fetch artifact content via download API.
        """
        try:
            content = await self.api_client.download_artifact(tenant_id, artifact_id)
            return content
        except Exception as e:
            logger.warning(
                "failed_to_download_artifact", artifact_id=artifact_id, error=str(e)
            )
            return None

    async def _extract_artifact_content(
        self, artifacts: list[dict[str, Any]], name: str, tenant_id: str
    ) -> str | None:
        """
        Extract content from a specific artifact by name.
        Handles both plain text and nested JSON format:
        - 'Alert Summary' artifacts: extract 'summary' field
        - 'Detailed Description' artifacts: extract 'analysis' field
        - Other artifacts: return as-is (plain text or full JSON)
        """
        import json

        for artifact in artifacts:
            if artifact.get("name") == name:
                content = artifact.get("content")
                if content is not None:
                    logger.debug(
                        "artifact_found", name=name, content_preview=content[:100]
                    )

                    # Try to parse as JSON and extract relevant field
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            # Extract 'summary' field for Alert Summary artifacts
                            if "summary" in parsed:
                                summary = parsed["summary"]
                                logger.debug("extracted_summary", preview=summary[:100])
                                return summary
                            # Extract 'analysis' field for Detailed Description artifacts
                            if "analysis" in parsed:
                                analysis = parsed["analysis"]
                                logger.debug(
                                    "extracted_analysis", preview=analysis[:100]
                                )
                                return analysis
                    except (json.JSONDecodeError, TypeError):
                        # Not JSON or not parseable - treat as plain text
                        pass

                    # Return as-is if not nested JSON format (backward compatibility)
                    return content
                # Content is null, need to fetch via download
                artifact_id = artifact.get("id")
                if artifact_id:
                    logger.debug(
                        "artifact_content_null_fetching_via_download",
                        name=name,
                    )
                    downloaded_content = await self._fetch_artifact_content(
                        tenant_id, artifact_id
                    )
                    if downloaded_content:
                        logger.debug(
                            "artifact_downloaded_successfully",
                            name=name,
                            content_preview=downloaded_content[:100],
                        )
                        # Apply same JSON parsing logic to downloaded content
                        try:
                            parsed = json.loads(downloaded_content)
                            if isinstance(parsed, dict):
                                if "summary" in parsed:
                                    return parsed["summary"]
                                if "analysis" in parsed:
                                    return parsed["analysis"]
                        except (json.JSONDecodeError, TypeError):
                            pass
                        return downloaded_content
                    logger.warning("artifact_download_failed", name=name)
                    return ""
                logger.warning(
                    "artifact_has_no_content_and_no_id",
                    name=name,
                )
                return ""

        logger.warning("artifact_not_found_in_workflow_outputs", name=name)
        return None

    @staticmethod
    def _find_fallback_disposition(
        dispositions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Find the 'Insufficient Data' disposition as a fallback.

        When the workflow doesn't produce a Disposition artifact (e.g., HITL
        workflow without detailed analysis), use this rather than leaving
        the alert with no disposition.
        """
        # Prefer "Insufficient Data" by name
        for disp in dispositions:
            if disp.get("display_name", "").lower() == "insufficient data":
                return {
                    "id": disp["disposition_id"],
                    "name": disp["display_name"],
                    "category": disp.get("category"),
                    "subcategory": disp.get("subcategory"),
                    "confidence": 0,
                }
        # Fall back to any Undetermined disposition
        for disp in dispositions:
            if disp.get("category", "").lower() == "undetermined":
                return {
                    "id": disp["disposition_id"],
                    "name": disp["display_name"],
                    "category": disp.get("category"),
                    "subcategory": disp.get("subcategory"),
                    "confidence": 0,
                }
        return None

    async def _match_disposition(
        self,
        disposition_text: str | None,
        dispositions: list[dict[str, Any]],
        confidence: int = 75,
    ) -> dict[str, Any]:
        """
        Match disposition text to an actual disposition record.

        Matching strategy (ordered by priority):
        1. Parse structured "CATEGORY / DISPLAY_NAME" format from LLM output
        2. Exact display_name match (case-insensitive)
        3. Keyword-based category matching ("true positive", "false positive")

        Raises ValueError if no match is found — silent defaulting hides real
        problems. The analysis workflow should produce a clear disposition; if
        Step 4 can't map it, that's a bug that must be visible.
        """
        if not disposition_text or not disposition_text.strip():
            raise ValueError(
                "No disposition text provided by workflow. "
                "The Disposition artifact is missing or empty."
            )

        # Strategy 1: Parse "CATEGORY / DISPLAY_NAME" structured format
        # Real LLM output: "TRUE POSITIVE (Malicious) / Malicious Attempt Blocked"
        if "/" in disposition_text:
            parts = disposition_text.split("/")
            # The display name is the last part (handles "A / B / C" formats)
            candidate_name = parts[-1].strip()

            for disp in dispositions:
                if disp.get("display_name", "").lower() == candidate_name.lower():
                    logger.info(
                        "structured_format_match",
                        candidate_name=candidate_name,
                        display_name=disp["display_name"],
                    )
                    return {
                        "id": disp["disposition_id"],
                        "name": disp["display_name"],
                        "category": disp.get("category"),
                        "subcategory": disp.get("subcategory"),
                        "confidence": confidence,
                    }

        # Strategy 2: Exact display_name match (case-insensitive)
        disposition_text_lower = disposition_text.lower().strip()
        for disp in dispositions:
            if disp.get("display_name", "").lower() == disposition_text_lower:
                logger.info("exact_name_match", display_name=disp["display_name"])
                return {
                    "id": disp["disposition_id"],
                    "name": disp["display_name"],
                    "category": disp.get("category"),
                    "subcategory": disp.get("subcategory"),
                    "confidence": confidence,
                }

        # Strategy 3: Display name as substring (e.g., "True Positive - Confirmed Compromise with 90% confidence")
        for disp in dispositions:
            display_name = disp.get("display_name", "").lower()
            if display_name and display_name in disposition_text_lower:
                logger.info("substring_match", display_name=disp["display_name"])
                return {
                    "id": disp["disposition_id"],
                    "name": disp["display_name"],
                    "category": disp.get("category"),
                    "subcategory": disp.get("subcategory"),
                    "confidence": confidence,
                }

        # No match — fail clearly
        available = [d.get("display_name") for d in dispositions]
        raise ValueError(
            f"No disposition match found for: '{disposition_text}'. "
            f"Available dispositions: {available}"
        )

    def _extract_confidence(self, text: str) -> int:
        """
        Extract confidence percentage from text.
        Looks for patterns like "85% confidence" or "confidence: 85"
        """
        if not text:
            return 75  # Default confidence

        # Look for percentage patterns
        patterns = [
            r"(-?\d+)%\s*confidence",
            r"confidence[:\s]+(-?\d+)%?",
            r"(-?\d+)\s*percent\s*confidence",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                confidence = int(match.group(1))
                # Ensure confidence is between 0 and 100
                return min(max(confidence, 0), 100)

        # Default confidence if no pattern found
        return 75

    async def _complete_analysis(
        self,
        tenant_id: str,
        analysis_id: str,
        disposition_id: str,
        confidence: int,
        short_summary: str | None,
        long_summary: str | None,
        workflow_run_id: str,
        workflow_id: str | None = None,
        disposition_category: str | None = None,
        disposition_subcategory: str | None = None,
        disposition_display_name: str | None = None,
        disposition_confidence: int | None = None,
    ):
        """
        Complete alert analysis via REST API to ensure consistent state.
        """
        logger.info(
            "completing_alert_analysis",
            analysis_id=analysis_id,
            disposition_id=disposition_id,
        )

        try:
            # Use the already-initialized API client (supports test mocking)
            async with InternalAsyncClient(
                base_url=self.api_client.base_url,
                timeout=self.api_client.timeout,
                headers=internal_auth_headers(),
            ) as client:
                response = await client.put(
                    f"/v1/{tenant_id}/analyses/{analysis_id}/complete",
                    json={
                        "disposition_id": str(disposition_id)
                        if disposition_id
                        else None,
                        "confidence": confidence,
                        "short_summary": short_summary or "",
                        "long_summary": long_summary or "",
                        "workflow_run_id": str(workflow_run_id)
                        if workflow_run_id
                        else None,
                        "workflow_id": str(workflow_id) if workflow_id else None,
                        "disposition_category": disposition_category,
                        "disposition_subcategory": disposition_subcategory,
                        "disposition_display_name": disposition_display_name,
                        "disposition_confidence": disposition_confidence,
                    },
                )
                response.raise_for_status()

            logger.info(
                "successfully_completed_analysis_via_api", analysis_id=analysis_id
            )

        except Exception as e:
            logger.error("failed_to_complete_alert_analysis_via_api", error=str(e))
            raise


# Alias for backward compatibility
DispositionMatchingStep = FinalDispositionUpdateStep
