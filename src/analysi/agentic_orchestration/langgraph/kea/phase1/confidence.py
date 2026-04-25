"""Confidence determination for Runbook Matching.

Deterministic threshold-based confidence from match scores.
"""

from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence level for runbook matching."""

    VERY_HIGH = "very_high"  # Exact detection rule match, score ≥170
    HIGH = "high"  # Strong match, score ≥120
    MEDIUM = "medium"  # Moderate match, score 70-119
    LOW = "low"  # Weak match, score 40-69
    VERY_LOW = "very_low"  # Minimal match, score <40


# Threshold configuration
THRESHOLDS = {
    "very_high_with_exact": 170,  # Requires exact_detection_rule match
    "high": 120,
    "medium": 70,
    "low": 40,
}


def determine_confidence(score: float, has_exact_rule: bool = False) -> ConfidenceLevel:
    """Determine confidence level from score.

    Args:
        score: Match score from RunbookMatcher.
        has_exact_rule: Whether there was an exact detection_rule match.

    Returns:
        ConfidenceLevel based on thresholds.

    Examples:
        >>> determine_confidence(180, has_exact_rule=True)
        ConfidenceLevel.VERY_HIGH
        >>> determine_confidence(150, has_exact_rule=False)
        ConfidenceLevel.HIGH
        >>> determine_confidence(80)
        ConfidenceLevel.MEDIUM
    """
    # VERY_HIGH requires both high score AND exact rule match
    if score >= THRESHOLDS["very_high_with_exact"] and has_exact_rule:
        return ConfidenceLevel.VERY_HIGH

    # HIGH threshold
    if score >= THRESHOLDS["high"]:
        return ConfidenceLevel.HIGH

    # MEDIUM threshold
    if score >= THRESHOLDS["medium"]:
        return ConfidenceLevel.MEDIUM

    # LOW threshold
    if score >= THRESHOLDS["low"]:
        return ConfidenceLevel.LOW

    # Below all thresholds
    return ConfidenceLevel.VERY_LOW


def should_use_match_path(confidence: ConfidenceLevel) -> bool:
    """Check if confidence level should use match path (vs composition).

    Args:
        confidence: Confidence level.

    Returns:
        True if HIGH or VERY_HIGH (use match path), False otherwise.
    """
    return confidence in (ConfidenceLevel.VERY_HIGH, ConfidenceLevel.HIGH)
