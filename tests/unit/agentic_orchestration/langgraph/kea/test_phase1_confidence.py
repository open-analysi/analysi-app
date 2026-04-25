"""Tests for confidence determination."""

from analysi.agentic_orchestration.langgraph.kea.phase1.confidence import (
    THRESHOLDS,
    ConfidenceLevel,
    determine_confidence,
    should_use_match_path,
)


class TestConfidenceThresholds:
    """Tests for threshold-based confidence."""

    def test_very_high_exact_rule(self):
        """Score ≥170 + exact rule = VERY_HIGH."""
        result = determine_confidence(180, has_exact_rule=True)
        assert result == ConfidenceLevel.VERY_HIGH

    def test_very_high_requires_exact_rule(self):
        """Score ≥170 without exact rule is HIGH, not VERY_HIGH."""
        result = determine_confidence(180, has_exact_rule=False)
        assert result == ConfidenceLevel.HIGH

    def test_high_confidence(self):
        """Score ≥120 = HIGH."""
        result = determine_confidence(150, has_exact_rule=False)
        assert result == ConfidenceLevel.HIGH

    def test_high_confidence_boundary(self):
        """Score exactly 120 = HIGH."""
        result = determine_confidence(120, has_exact_rule=False)
        assert result == ConfidenceLevel.HIGH

    def test_medium_confidence(self):
        """Score 70-119 = MEDIUM."""
        result = determine_confidence(90, has_exact_rule=False)
        assert result == ConfidenceLevel.MEDIUM

    def test_medium_confidence_boundary_low(self):
        """Score exactly 70 = MEDIUM."""
        result = determine_confidence(70, has_exact_rule=False)
        assert result == ConfidenceLevel.MEDIUM

    def test_medium_confidence_boundary_high(self):
        """Score 119 = MEDIUM (just below HIGH)."""
        result = determine_confidence(119, has_exact_rule=False)
        assert result == ConfidenceLevel.MEDIUM

    def test_low_confidence(self):
        """Score 40-69 = LOW."""
        result = determine_confidence(50, has_exact_rule=False)
        assert result == ConfidenceLevel.LOW

    def test_low_confidence_boundary(self):
        """Score exactly 40 = LOW."""
        result = determine_confidence(40, has_exact_rule=False)
        assert result == ConfidenceLevel.LOW

    def test_very_low_confidence(self):
        """Score <40 = VERY_LOW."""
        result = determine_confidence(30, has_exact_rule=False)
        assert result == ConfidenceLevel.VERY_LOW

    def test_very_low_zero(self):
        """Score 0 = VERY_LOW."""
        result = determine_confidence(0, has_exact_rule=False)
        assert result == ConfidenceLevel.VERY_LOW


class TestPathSelection:
    """Tests for match vs composition path selection."""

    def test_match_path_very_high(self):
        """VERY_HIGH routes to match path."""
        assert should_use_match_path(ConfidenceLevel.VERY_HIGH) is True

    def test_match_path_high(self):
        """HIGH routes to match path."""
        assert should_use_match_path(ConfidenceLevel.HIGH) is True

    def test_compose_path_medium(self):
        """MEDIUM routes to composition."""
        assert should_use_match_path(ConfidenceLevel.MEDIUM) is False

    def test_compose_path_low(self):
        """LOW routes to composition."""
        assert should_use_match_path(ConfidenceLevel.LOW) is False

    def test_compose_path_very_low(self):
        """VERY_LOW routes to composition."""
        assert should_use_match_path(ConfidenceLevel.VERY_LOW) is False


class TestThresholdsConfig:
    """Tests for threshold configuration."""

    def test_thresholds_exist(self):
        """Threshold constants are defined."""
        assert "very_high_with_exact" in THRESHOLDS
        assert "high" in THRESHOLDS
        assert "medium" in THRESHOLDS
        assert "low" in THRESHOLDS

    def test_thresholds_ordered(self):
        """Thresholds are in descending order."""
        assert THRESHOLDS["very_high_with_exact"] > THRESHOLDS["high"]
        assert THRESHOLDS["high"] > THRESHOLDS["medium"]
        assert THRESHOLDS["medium"] > THRESHOLDS["low"]
