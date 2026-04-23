"""
Cy Native Functions for Alert Enrichment.

Provides functions to simplify adding enrichment data to alerts.
"""

from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)


class CyEnrichmentFunctions:
    """Functions for enriching alerts with task output."""

    def __init__(self, execution_context: dict[str, Any]):
        """
        Initialize enrichment functions with execution context.

        Args:
            execution_context: Task/workflow execution context containing cy_name
        """
        self.execution_context = execution_context

    def enrich_alert(
        self, alert: dict[str, Any], enrichment_data: Any, key_name: str | None = None
    ) -> dict[str, Any]:
        """
        Add enrichment data to alert under a specified key or task's cy_name.

        This simplifies the common pattern of adding task output to an alert's
        enrichments dictionary. The enrichment is stored under the provided key_name,
        or falls back to the task's cy_name for clear attribution.

        Args:
            alert: The alert dict to enrich (typically `input` in Cy script)
            enrichment_data: Data to store in enrichments (any JSON-serializable value)
            key_name: Optional custom key name. If not provided, uses task's cy_name.

        Returns:
            The modified alert dict with enrichment added under alert["enrichments"][key]

        Example Cy usage:
            ```cy
            # Auto key from cy_name
            return enrich_alert(input, {"score": 95})

            # Custom key
            return enrich_alert(input, {"score": 95}, "virustotal_result")
            ```
        """
        # Use provided key_name, or fall back to cy_name, or "unknown_task"
        if key_name:
            enrichment_key = key_name
        else:
            enrichment_key = self.execution_context.get("cy_name")
            if not enrichment_key:
                enrichment_key = "unknown_task"
                logger.warning(
                    "enrich_alert called without cy_name in execution context"
                )

        # Safety: ensure alert is a dict
        if not isinstance(alert, dict):
            logger.error(
                "enrichalert_alert_must_be_dict_got", alert_type=type(alert).__name__
            )
            return alert

        # Safety: ensure enrichments dict exists and is valid
        enrichments = alert.get("enrichments")
        if enrichments is None:
            enrichments = {}
        elif not isinstance(enrichments, dict):
            logger.warning(
                "enrich_alert_replacing_enrichments",
                enrichments_type=type(enrichments).__name__,
            )
            enrichments = {}

        # Add enrichment under the specified key
        enrichments[enrichment_key] = enrichment_data
        alert["enrichments"] = enrichments

        return alert


def create_cy_enrichment_functions(
    execution_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Create dictionary of enrichment functions for Cy interpreter.

    Args:
        execution_context: Execution context containing cy_name

    Returns:
        Dictionary mapping function names to callables
    """
    enrichment_functions = CyEnrichmentFunctions(execution_context)

    # Create wrapper function for enrichment
    def enrich_alert_wrapper(
        alert: dict[str, Any], enrichment_data: Any, key_name: str | None = None
    ) -> dict[str, Any]:
        """Cy-compatible wrapper for enriching alerts."""
        return enrichment_functions.enrich_alert(alert, enrichment_data, key_name)

    return {
        "enrich_alert": enrich_alert_wrapper,
    }
