"""Unit tests for Cy Enrichment Functions."""

import pytest

from analysi.services.cy_enrichment_functions import (
    CyEnrichmentFunctions,
    create_cy_enrichment_functions,
)


class TestCyEnrichmentFunctions:
    """Test suite for CyEnrichmentFunctions class."""

    @pytest.fixture
    def execution_context(self):
        """Create execution context with cy_name."""
        return {
            "cy_name": "vt_ip_lookup",
            "task_id": "test-task-id",
            "tenant_id": "test-tenant",
        }

    @pytest.fixture
    def cy_enrichment_functions(self, execution_context):
        """Create CyEnrichmentFunctions instance."""
        return CyEnrichmentFunctions(execution_context=execution_context)

    def test_enrich_alert_adds_enrichment(self, cy_enrichment_functions):
        """Basic enrichment adds data under cy_name key."""
        alert = {"title": "Test Alert", "severity": "high"}
        enrichment_data = {"score": 85, "malicious": True}

        result = cy_enrichment_functions.enrich_alert(alert, enrichment_data)

        assert result["enrichments"]["vt_ip_lookup"] == {"score": 85, "malicious": True}
        assert result["title"] == "Test Alert"  # Original preserved
        assert result["severity"] == "high"  # Original preserved

    def test_enrich_alert_preserves_existing_enrichments(self, cy_enrichment_functions):
        """Existing enrichments are preserved when adding new ones."""
        alert = {
            "title": "Test",
            "enrichments": {"previous_task": {"data": "old_value"}},
        }
        enrichment_data = {"new": "data"}

        result = cy_enrichment_functions.enrich_alert(alert, enrichment_data)

        assert result["enrichments"]["previous_task"] == {"data": "old_value"}
        assert result["enrichments"]["vt_ip_lookup"] == {"new": "data"}

    def test_enrich_alert_handles_null_enrichments(self, cy_enrichment_functions):
        """Alert with null enrichments gets new dict."""
        alert = {"title": "Test", "enrichments": None}

        result = cy_enrichment_functions.enrich_alert(alert, "simple_value")

        assert result["enrichments"]["vt_ip_lookup"] == "simple_value"

    def test_enrich_alert_handles_missing_enrichments_key(
        self, cy_enrichment_functions
    ):
        """Alert without enrichments key gets new dict."""
        alert = {"title": "Test"}

        result = cy_enrichment_functions.enrich_alert(alert, {"data": 123})

        assert result["enrichments"]["vt_ip_lookup"] == {"data": 123}

    def test_enrich_alert_uses_fallback_without_cy_name(self):
        """Missing cy_name uses 'unknown_task' fallback."""
        context = {}  # No cy_name
        funcs = CyEnrichmentFunctions(context)

        alert = {"title": "Test"}
        result = funcs.enrich_alert(alert, {"data": 1})

        assert result["enrichments"]["unknown_task"] == {"data": 1}

    def test_enrich_alert_returns_non_dict_unchanged(self, cy_enrichment_functions):
        """Non-dict input returned unchanged with error logged."""
        result = cy_enrichment_functions.enrich_alert("not a dict", {"data": 1})

        assert result == "not a dict"

    def test_enrich_alert_handles_non_dict_enrichments(self, cy_enrichment_functions):
        """Non-dict enrichments value is replaced with empty dict."""
        alert = {"title": "Test", "enrichments": "invalid_string"}

        result = cy_enrichment_functions.enrich_alert(alert, {"score": 90})

        assert result["enrichments"] == {"vt_ip_lookup": {"score": 90}}

    def test_enrich_alert_with_list_enrichments(self, cy_enrichment_functions):
        """List enrichments value is replaced with empty dict."""
        alert = {"title": "Test", "enrichments": [1, 2, 3]}

        result = cy_enrichment_functions.enrich_alert(alert, "value")

        assert result["enrichments"] == {"vt_ip_lookup": "value"}

    def test_enrich_alert_overwrites_same_cy_name(self, cy_enrichment_functions):
        """Calling enrich_alert twice with same cy_name overwrites."""
        alert = {"title": "Test", "enrichments": {"vt_ip_lookup": {"old": "data"}}}

        result = cy_enrichment_functions.enrich_alert(alert, {"new": "data"})

        assert result["enrichments"]["vt_ip_lookup"] == {"new": "data"}

    def test_enrich_alert_with_complex_enrichment_data(self, cy_enrichment_functions):
        """Complex nested enrichment data is preserved."""
        alert = {"title": "Test"}
        enrichment_data = {
            "score": 95,
            "details": {
                "ip_info": {"country": "US", "asn": 12345},
                "categories": ["malware", "phishing"],
            },
            "raw_response": {"status": "ok", "data": [1, 2, 3]},
        }

        result = cy_enrichment_functions.enrich_alert(alert, enrichment_data)

        assert result["enrichments"]["vt_ip_lookup"] == enrichment_data
        assert (
            result["enrichments"]["vt_ip_lookup"]["details"]["ip_info"]["country"]
            == "US"
        )

    def test_enrich_alert_with_none_enrichment_data(self, cy_enrichment_functions):
        """None enrichment data is stored as None."""
        alert = {"title": "Test"}

        result = cy_enrichment_functions.enrich_alert(alert, None)

        assert result["enrichments"]["vt_ip_lookup"] is None

    def test_enrich_alert_modifies_original_alert(self, cy_enrichment_functions):
        """enrich_alert modifies the original alert dict (by design)."""
        alert = {"title": "Test"}

        result = cy_enrichment_functions.enrich_alert(alert, {"data": 1})

        # Both should reference same dict
        assert alert is result
        assert alert["enrichments"]["vt_ip_lookup"] == {"data": 1}

    def test_enrich_alert_with_custom_key_name(self, cy_enrichment_functions):
        """Custom key_name overrides cy_name from context."""
        alert = {"title": "Test"}

        result = cy_enrichment_functions.enrich_alert(
            alert, {"score": 90}, key_name="custom_key"
        )

        # Should use custom key, not cy_name from context
        assert "custom_key" in result["enrichments"]
        assert result["enrichments"]["custom_key"] == {"score": 90}
        assert "vt_ip_lookup" not in result["enrichments"]

    def test_enrich_alert_custom_key_without_cy_name_in_context(self):
        """Custom key_name works even without cy_name in context."""
        context = {}  # No cy_name
        funcs = CyEnrichmentFunctions(context)

        alert = {"title": "Test"}
        result = funcs.enrich_alert(alert, {"data": 1}, key_name="my_custom_key")

        assert result["enrichments"]["my_custom_key"] == {"data": 1}
        assert "unknown_task" not in result["enrichments"]

    def test_enrich_alert_custom_key_preserves_existing(self, cy_enrichment_functions):
        """Custom key_name preserves existing enrichments."""
        alert = {
            "title": "Test",
            "enrichments": {"existing_task": {"old": "data"}},
        }

        result = cy_enrichment_functions.enrich_alert(
            alert, {"new": "data"}, key_name="new_task"
        )

        assert result["enrichments"]["existing_task"] == {"old": "data"}
        assert result["enrichments"]["new_task"] == {"new": "data"}


class TestCreateCyEnrichmentFunctions:
    """Test factory function."""

    def test_creates_enrich_alert_wrapper(self):
        """Factory returns dict with enrich_alert function."""
        context = {"cy_name": "my_task"}
        funcs = create_cy_enrichment_functions(context)

        assert "enrich_alert" in funcs
        assert callable(funcs["enrich_alert"])

    def test_wrapper_works_correctly(self):
        """Wrapper function behaves same as class method."""
        context = {"cy_name": "wrapper_test"}
        funcs = create_cy_enrichment_functions(context)

        alert = {"title": "Test"}
        result = funcs["enrich_alert"](alert, {"enriched": True})

        assert result["enrichments"]["wrapper_test"] == {"enriched": True}

    def test_wrapper_preserves_existing_enrichments(self):
        """Wrapper preserves existing enrichments."""
        context = {"cy_name": "new_task"}
        funcs = create_cy_enrichment_functions(context)

        alert = {"title": "Test", "enrichments": {"old_task": {"old": "data"}}}
        result = funcs["enrich_alert"](alert, {"new": "data"})

        assert result["enrichments"]["old_task"] == {"old": "data"}
        assert result["enrichments"]["new_task"] == {"new": "data"}

    def test_multiple_calls_with_different_contexts(self):
        """Multiple wrappers with different contexts work independently."""
        context1 = {"cy_name": "task_a"}
        context2 = {"cy_name": "task_b"}

        funcs1 = create_cy_enrichment_functions(context1)
        funcs2 = create_cy_enrichment_functions(context2)

        alert = {"title": "Test"}

        funcs1["enrich_alert"](alert, {"from": "task_a"})
        funcs2["enrich_alert"](alert, {"from": "task_b"})

        assert alert["enrichments"]["task_a"] == {"from": "task_a"}
        assert alert["enrichments"]["task_b"] == {"from": "task_b"}
