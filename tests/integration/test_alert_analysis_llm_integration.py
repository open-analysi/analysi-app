"""Integration tests for Alert Analysis disposition matching."""

import pytest

from analysi.alert_analysis.steps.final_disposition_update import (
    FinalDispositionUpdateStep,
)


@pytest.mark.integration
class TestAlertAnalysisDispositionIntegration:
    """Test that Alert Analysis disposition matching works correctly."""

    @pytest.mark.asyncio
    async def test_disposition_step_stores_tenant_context(self):
        """Test that FinalDispositionUpdateStep stores tenant context correctly.

        The step uses text-matching (not LLM) for disposition matching,
        with a BackendAPIClient for API calls.
        """
        tenant_id = "tenant-with-custom-config"

        step = FinalDispositionUpdateStep(tenant_id=tenant_id)

        # Verify tenant context is stored
        assert step.tenant_id == tenant_id
        assert step.api_client is not None

        # Verify text-based disposition matching works
        dispositions = [
            {
                "disposition_id": "d1",
                "display_name": "Confirmed Compromise",
                "category": "True Positive",
                "subcategory": "Malicious",
            },
            {
                "disposition_id": "d2",
                "display_name": "Suspicious Activity",
                "category": "Inconclusive",
                "subcategory": None,
            },
        ]
        result = await step._match_disposition("Confirmed Compromise", dispositions)
        assert result["id"] == "d1"
        assert result["name"] == "Confirmed Compromise"
