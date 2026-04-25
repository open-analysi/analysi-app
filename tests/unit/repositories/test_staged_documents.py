"""Unit tests for staged document schema and logic (no DB).

Tests pure functions and constants only.
"""

from analysi.models.kdg_edge import EdgeType


class TestEdgeTypeConstant:
    """Test that STAGED_FOR constant exists."""

    def test_staged_for_constant(self):
        """T0: EdgeType has STAGED_FOR constant."""
        assert EdgeType.STAGED_FOR == "staged_for"


class TestExtractionEligibility:
    """Tests for extraction_eligible flag."""

    def test_runbooks_manager_eligible(self):
        """T7: runbooks-manager skill has extraction_eligible=True."""
        from analysi.schemas.skill import is_extraction_eligible

        assert is_extraction_eligible("runbooks_manager") is True

    def test_other_skill_not_eligible(self):
        """T7b: Other skills have extraction_eligible=False."""
        from analysi.schemas.skill import is_extraction_eligible

        assert is_extraction_eligible("some_other_skill") is False
        assert is_extraction_eligible(None) is False
