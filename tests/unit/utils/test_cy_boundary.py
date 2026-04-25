"""Unit tests for the shared Cy-boundary adapter simulator.

These pin the contract that integration-action tests rely on. If production
behavior changes in `services/task_execution.py`, update `tests/utils/cy_boundary.py`
AND these tests together.
"""

import pytest

from tests.utils.cy_boundary import apply_cy_adapter


class TestCyBoundaryAdapter:
    @pytest.mark.unit
    def test_non_dict_passes_through(self):
        assert apply_cy_adapter([1, 2, 3]) == [1, 2, 3]
        assert apply_cy_adapter("hello") == "hello"
        assert apply_cy_adapter(42) == 42

    @pytest.mark.unit
    def test_error_result_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="ValidationError: bad input"):
            apply_cy_adapter(
                {
                    "status": "error",
                    "error": "bad input",
                    "error_type": "ValidationError",
                }
            )

    @pytest.mark.unit
    def test_error_result_uses_fallbacks(self):
        with pytest.raises(RuntimeError, match="IntegrationError: Unknown error"):
            apply_cy_adapter({"status": "error"})

    @pytest.mark.unit
    def test_envelope_keys_stripped(self):
        # Multi-field so single-field-unwrap doesn't fire — want to observe
        # that status/timestamp/integration_id/action_id are all removed.
        result = apply_cy_adapter(
            {
                "status": "success",
                "timestamp": "2025-01-01T00:00:00Z",
                "integration_id": "vt",
                "action_id": "lookup",
                "score": 85,
                "country": "US",
            }
        )
        assert result == {"score": 85, "country": "US"}

    @pytest.mark.unit
    def test_data_unwrapped_when_no_siblings(self):
        result = apply_cy_adapter(
            {"status": "success", "data": {"entries": [{"id": 1}]}}
        )
        assert result == {"entries": [{"id": 1}]}

    @pytest.mark.unit
    def test_siblings_merged_into_data(self):
        result = apply_cy_adapter(
            {
                "status": "success",
                "data": {"entries": [{"id": 1}]},
                "total_objects": 1,
                "not_found": False,
            }
        )
        assert result == {
            "entries": [{"id": 1}],
            "total_objects": 1,
            "not_found": False,
        }

    @pytest.mark.unit
    def test_not_found_idiom_preserved(self):
        """The `success_result(not_found=True, data=X)` pattern reaches Cy intact."""
        result = apply_cy_adapter(
            {
                "status": "success",
                "timestamp": "...",
                "integration_id": "vt",
                "action_id": "ip_reputation",
                "not_found": True,
                "data": {"ip": "1.2.3.4"},
            }
        )
        assert result == {"not_found": True, "ip": "1.2.3.4"}

    @pytest.mark.unit
    def test_data_key_wins_on_conflict(self):
        result = apply_cy_adapter(
            {
                "status": "success",
                "data": {"cached": True, "value": 10},
                "cached": False,
            }
        )
        # data's "cached": True wins over sibling "cached": False
        assert result == {"cached": True, "value": 10}

    @pytest.mark.unit
    def test_list_data_dropps_siblings(self):
        """When data is a list, siblings cannot be merged and are dropped."""
        result = apply_cy_adapter(
            {
                "status": "success",
                "data": [{"id": 1}, {"id": 2}],
                "not_found": True,  # lost — author should put inside data
            }
        )
        assert result == [{"id": 1}, {"id": 2}]

    @pytest.mark.unit
    def test_flat_shape_multi_field(self):
        """Flat-style action (no `data` key) returns stripped dict as-is."""
        result = apply_cy_adapter(
            {
                "status": "success",
                "ip_address": "1.2.3.4",
                "reputation_summary": {"malicious": 0},
                "network_info": {"asn": "AS15169"},
            }
        )
        assert result == {
            "ip_address": "1.2.3.4",
            "reputation_summary": {"malicious": 0},
            "network_info": {"asn": "AS15169"},
        }

    @pytest.mark.unit
    def test_legacy_single_field_unwrapped(self):
        """Single remaining field after strip — unwrap to its value (backward compat)."""
        result = apply_cy_adapter(
            {
                "status": "success",
                "timestamp": "...",
                "spl_query": "search index=main",
            }
        )
        assert result == "search index=main"
