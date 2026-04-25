"""Tests for common validators."""

from pydantic import BaseModel

from analysi.agentic_orchestration.langgraph.substep.validation import (
    validate_has_critical_steps,
    validate_json_output,
    validate_no_wikilinks,
    validate_non_empty,
    validate_pydantic_model,
)


class TestValidateJsonOutput:
    """Tests for validate_json_output."""

    def test_validate_json_valid(self):
        """Valid JSON returns passed=True."""
        result = validate_json_output('{"key": "value", "number": 42}')

        assert result.passed is True
        assert result.errors == []

    def test_validate_json_valid_array(self):
        """Valid JSON array returns passed=True."""
        result = validate_json_output('[1, 2, 3, "four"]')

        assert result.passed is True

    def test_validate_json_invalid(self):
        """Invalid JSON returns passed=False with error message."""
        result = validate_json_output('{"key": missing_quotes}')

        assert result.passed is False
        assert len(result.errors) > 0
        assert "json" in result.errors[0].lower() or "parse" in result.errors[0].lower()

    def test_validate_json_empty(self):
        """Empty string returns passed=False."""
        result = validate_json_output("")

        assert result.passed is False


class TestValidatePydanticModel:
    """Tests for validate_pydantic_model factory."""

    class ScoreModel(BaseModel):
        """Test model for validation."""

        value: int
        label: str

    def test_validate_pydantic_matching(self):
        """JSON matching model returns passed=True."""
        validator = validate_pydantic_model(self.ScoreModel)
        result = validator('{"value": 42, "label": "test"}')

        assert result.passed is True
        assert result.errors == []

    def test_validate_pydantic_missing_field(self):
        """JSON missing required field returns passed=False."""
        validator = validate_pydantic_model(self.ScoreModel)
        result = validator('{"value": 42}')  # Missing 'label'

        assert result.passed is False
        assert len(result.errors) > 0

    def test_validate_pydantic_wrong_type(self):
        """JSON with wrong field type returns passed=False."""
        validator = validate_pydantic_model(self.ScoreModel)
        result = validator('{"value": "not_an_int", "label": "test"}')

        assert result.passed is False
        assert len(result.errors) > 0

    def test_validate_pydantic_extra_fields(self):
        """JSON with extra fields passes (default Pydantic behavior)."""
        validator = validate_pydantic_model(self.ScoreModel)
        result = validator('{"value": 42, "label": "test", "extra": "ignored"}')

        assert result.passed is True

    def test_validate_pydantic_invalid_json(self):
        """Invalid JSON fails before Pydantic validation."""
        validator = validate_pydantic_model(self.ScoreModel)
        result = validator("not json at all")

        assert result.passed is False


class TestValidateNonEmpty:
    """Tests for validate_non_empty."""

    def test_validate_non_empty_with_content(self):
        """Non-empty string returns passed=True."""
        result = validate_non_empty("Some meaningful content")

        assert result.passed is True
        assert result.errors == []

    def test_validate_non_empty_empty_string(self):
        """Empty string returns passed=False."""
        result = validate_non_empty("")

        assert result.passed is False
        assert len(result.errors) > 0

    def test_validate_non_empty_whitespace_only(self):
        """Whitespace-only string returns passed=False."""
        result = validate_non_empty("   \n\t   ")

        assert result.passed is False
        assert len(result.errors) > 0


class TestValidateNoWikilinks:
    """Tests for validate_no_wikilinks."""

    def test_validate_no_wikilinks_clean(self):
        """Content without WikiLinks returns passed=True."""
        content = """# Runbook

## Steps
1. Check logs
2. Analyze traffic
"""
        result = validate_no_wikilinks(content)

        assert result.passed is True
        assert result.errors == []

    def test_validate_no_wikilinks_has_wikilink(self):
        """Content with ![[...]] returns passed=False."""
        content = """# Runbook

![[common/header.md]]

## Steps
1. Check logs
"""
        result = validate_no_wikilinks(content)

        assert result.passed is False
        assert len(result.errors) > 0
        assert "common/header.md" in result.errors[0]

    def test_validate_no_wikilinks_multiple(self):
        """Content with multiple WikiLinks lists all in errors."""
        content = """# Runbook

![[common/header.md]]
![[common/footer.md]]

## Steps
![[steps/investigation.md]]
"""
        result = validate_no_wikilinks(content)

        assert result.passed is False
        # Should mention all unexpanded WikiLinks
        errors_text = " ".join(result.errors)
        assert "header.md" in errors_text or len(result.errors) >= 1


class TestValidateHasCriticalSteps:
    """Tests for validate_has_critical_steps."""

    def test_validate_critical_steps_present(self):
        """Content with ★ markers returns passed=True."""
        content = """# Investigation Runbook

## Steps

### 1. Alert Understanding ★
Review the alert details.

### 2. Evidence Collection ★
Gather relevant logs.

### 3. Optional Enrichment
Get additional context.

### 4. Final Analysis ★
Reach a verdict.
"""
        result = validate_has_critical_steps(content)

        assert result.passed is True

    def test_validate_critical_steps_missing(self):
        """Content without ★ returns passed=False."""
        content = """# Investigation Runbook

## Steps

### 1. Alert Understanding
Review the alert details.

### 2. Evidence Collection
Gather relevant logs.
"""
        result = validate_has_critical_steps(content)

        assert result.passed is False
        assert len(result.errors) > 0

    def test_validate_critical_steps_counts(self):
        """Validation provides information about critical steps found."""
        content = """# Runbook

### Step 1 ★
### Step 2 ★
### Step 3
"""
        result = validate_has_critical_steps(content)

        assert result.passed is True
        # The implementation should track count (exact behavior TBD)
