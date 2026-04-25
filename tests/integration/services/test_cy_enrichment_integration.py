"""Integration tests for Cy Enrichment Functions."""

import uuid

import pytest

from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyEnrichmentFunctionsIntegration:
    """Integration tests for enrich_alert() in Cy scripts."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_enrich_alert_basic_usage(self, integration_test_session, tenant_id):
        """Test basic enrich_alert usage in Cy script."""
        executor = DefaultTaskExecutor()

        cy_script = """
enrichment = {"score": 95, "verdict": "clean"}
return enrich_alert(input, enrichment)
"""
        input_data = {"title": "Test Alert", "severity": "medium"}
        execution_context = {
            "cy_name": "test_enrichment_task",
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data=input_data,
            execution_context=execution_context,
        )

        assert result["status"] == "completed"

        # Parse the output (Cy returns Python repr string for dict outputs)
        output = parse_cy_output(result["output"])

        assert output["title"] == "Test Alert"
        assert output["severity"] == "medium"
        assert output["enrichments"]["test_enrichment_task"]["score"] == 95
        assert output["enrichments"]["test_enrichment_task"]["verdict"] == "clean"

    @pytest.mark.asyncio
    async def test_enrich_alert_preserves_existing_enrichments(
        self, integration_test_session, tenant_id
    ):
        """Test that enrich_alert preserves existing enrichments."""
        executor = DefaultTaskExecutor()

        cy_script = """
new_enrichment = {"new_data": "value"}
return enrich_alert(input, new_enrichment)
"""
        input_data = {
            "title": "Test Alert",
            "enrichments": {"previous_task": {"old_data": "old_value"}},
        }
        execution_context = {
            "cy_name": "second_task",
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data=input_data,
            execution_context=execution_context,
        )

        assert result["status"] == "completed"

        output = parse_cy_output(result["output"])

        # Both enrichments should be present
        assert output["enrichments"]["previous_task"]["old_data"] == "old_value"
        assert output["enrichments"]["second_task"]["new_data"] == "value"

    @pytest.mark.asyncio
    async def test_enrich_alert_with_complex_data(
        self, integration_test_session, tenant_id
    ):
        """Test enrich_alert with complex nested enrichment data."""
        executor = DefaultTaskExecutor()

        cy_script = """
enrichment = {
    "ip_reputation": {
        "score": 85,
        "country": "US",
        "categories": ["malware", "phishing"]
    },
    "raw_response": {
        "status": "ok",
        "data": [1, 2, 3]
    }
}
return enrich_alert(input, enrichment)
"""
        input_data = {"title": "Complex Test"}
        execution_context = {
            "cy_name": "complex_enrichment_task",
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data=input_data,
            execution_context=execution_context,
        )

        assert result["status"] == "completed"

        output = parse_cy_output(result["output"])

        enrichment = output["enrichments"]["complex_enrichment_task"]
        assert enrichment["ip_reputation"]["score"] == 85
        assert enrichment["ip_reputation"]["country"] == "US"
        assert "malware" in enrichment["ip_reputation"]["categories"]
        assert enrichment["raw_response"]["data"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_enrich_alert_without_cy_name_uses_fallback(
        self, integration_test_session, tenant_id
    ):
        """Test that missing cy_name uses 'unknown_task' fallback."""
        executor = DefaultTaskExecutor()

        cy_script = """
return enrich_alert(input, {"data": "test"})
"""
        input_data = {"title": "Test"}
        # No cy_name in context
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data=input_data,
            execution_context=execution_context,
        )

        assert result["status"] == "completed"

        output = parse_cy_output(result["output"])

        # Should use fallback key
        assert output["enrichments"]["unknown_task"]["data"] == "test"

    @pytest.mark.asyncio
    async def test_enrich_alert_typical_workflow_pattern(
        self, integration_test_session, tenant_id
    ):
        """Test typical workflow pattern: process input, enrich, return."""
        executor = DefaultTaskExecutor()

        # Simulates a real task that does some processing and enriches
        cy_script = """ioc = input.primary_ioc_value
enrichment = {"ioc_analyzed": ioc, "confidence": 0.95}
return enrich_alert(input, enrichment)"""

        input_data = {
            "title": "Suspicious IP Connection",
            "severity": "high",
            "primary_ioc_type": "ip",
            "primary_ioc_value": "192.168.1.100",
        }
        execution_context = {
            "cy_name": "threat_intel_enrichment",
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data=input_data,
            execution_context=execution_context,
        )

        if result["status"] == "failed":
            print(f"SCRIPT ERROR: {result.get('error')}")

        assert result["status"] == "completed"

        output = parse_cy_output(result["output"])

        # Original alert data preserved
        assert output["title"] == "Suspicious IP Connection"
        assert output["primary_ioc_value"] == "192.168.1.100"

        # Enrichment added under task's cy_name
        enrichment = output["enrichments"]["threat_intel_enrichment"]
        assert enrichment["ioc_analyzed"] == "192.168.1.100"
        assert enrichment["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_enrich_alert_with_custom_key_name(
        self, integration_test_session, tenant_id
    ):
        """Test enrich_alert with custom key_name parameter."""
        executor = DefaultTaskExecutor()

        cy_script = (
            """return enrich_alert(input, {"score": 100}, "custom_enrichment")"""
        )

        input_data = {"title": "Test Alert"}
        execution_context = {
            "cy_name": "original_task_name",
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

        result = await executor.execute(
            cy_script=cy_script,
            input_data=input_data,
            execution_context=execution_context,
        )

        assert result["status"] == "completed"

        output = parse_cy_output(result["output"])

        # Should use custom key, not cy_name
        assert "custom_enrichment" in output["enrichments"]
        assert output["enrichments"]["custom_enrichment"]["score"] == 100
        assert "original_task_name" not in output["enrichments"]
