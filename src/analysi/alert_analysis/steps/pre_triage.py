"""Step 1: Pre-triage implementation"""

from typing import Any

from analysi.config.logging import get_logger

logger = get_logger(__name__)


class PreTriageStep:
    """
    Pre-triage step for initial alert assessment.
    This step performs initial categorization and prioritization.

    STUBBED: Currently returns placeholder data
    """

    async def execute(
        self, tenant_id: str, alert_id: str, analysis_id: str, **kwargs
    ) -> dict[str, Any]:
        """
        Execute pre-triage analysis.

        Future implementation will:
        - Categorize alert severity
        - Check for known patterns
        - Determine initial priority

        Returns:
            Dict with pre-triage results
        """
        logger.info("executing_pretriage_for_alert", alert_id=alert_id)

        # STUBBED: Return placeholder results
        result = {
            "priority": "high",
            "category": "malware",
            "requires_immediate_action": True,
            "confidence": 0.85,
        }

        logger.info("pretriage_completed_priority", priority=result["priority"])
        return result
