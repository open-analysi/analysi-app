"""Tests for SubStep executor.

Uses MockResourceStore since skills are now DB-only.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore
from analysi.agentic_orchestration.langgraph.substep.definition import (
    SubStep,
    ValidationResult,
)
from analysi.agentic_orchestration.langgraph.substep.executor import (
    MaxRetriesExceededError,
    execute_substep,
)


class MockResourceStore(ResourceStore):
    """Test-only ResourceStore that reads from filesystem.

    This is used to test executor logic. Production code uses DatabaseResourceStore.
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir

    def list_skills(self) -> dict[str, str]:
        """List all skills in the directory."""
        skills = {}
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                # Extract description from frontmatter
                description = ""
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 2:
                        for line in parts[1].strip().split("\n"):
                            if line.startswith("description:"):
                                description = line.split(":", 1)[1].strip()
                                break
                skills[skill_dir.name] = description
        return skills

    def tree(self, skill: str) -> list[str]:
        """Get all file paths within a skill."""
        skill_dir = self.skills_dir / skill
        if not skill_dir.exists():
            return []
        paths = []
        for path in skill_dir.rglob("*"):
            if path.is_file():
                paths.append(str(path.relative_to(skill_dir)))
        return sorted(paths)

    def read(self, skill: str, path: str) -> str | None:
        """Read content of a file within a skill."""
        file_path = self.skills_dir / skill / path
        if not file_path.exists():
            return None
        return file_path.read_text()


@pytest.fixture
def temp_skills_dir() -> Path:
    """Create a temporary skills directory with test content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create test skill
        skill = skills_dir / "test-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: test-skill\n"
            "description: Test skill for executor tests.\n"
            "---\n\n"
            "# Test Skill\n"
            "This is test content for the skill."
        )
        (skill / "references").mkdir()
        (skill / "references" / "guide.md").write_text("# Guide\nDetailed guidance.")

        yield skills_dir


@pytest.fixture
def store(temp_skills_dir: Path) -> MockResourceStore:
    """Create store from temp directory."""
    return MockResourceStore(temp_skills_dir)


@pytest.fixture
def mock_llm():
    """Create mock LLM for testing."""
    mock = MagicMock()
    return mock


def always_pass(output: str) -> ValidationResult:
    """Validator that always passes."""
    return ValidationResult(passed=True)


def always_fail(output: str) -> ValidationResult:
    """Validator that always fails."""
    return ValidationResult(passed=False, errors=["Always fails"])


def fail_then_pass(attempts: list[int]):
    """Factory: validator that fails N times then passes."""

    def validator(output: str) -> ValidationResult:
        attempts[0] += 1
        if attempts[0] < 3:
            return ValidationResult(
                passed=False, errors=[f"Attempt {attempts[0]} failed"]
            )
        return ValidationResult(passed=True)

    return validator


def needs_more_context_validator(output: str) -> ValidationResult:
    """Validator that requests more context."""
    return ValidationResult(
        passed=False,
        errors=["Insufficient context"],
        needs_more_context=True,
        context_hint="load composition guide",
    )


class TestExecuteSubstepHappyPath:
    """Happy path tests for execute_substep."""

    @pytest.mark.asyncio
    async def test_execute_immediate_pass(self, store: MockResourceStore, mock_llm):
        """SubStep passes on first attempt."""
        # Mock LLM to return output
        mock_llm.ainvoke = AsyncMock(return_value="Generated output")
        # Mock SkillsIR retrieval (handled internally)
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        substep = SubStep(
            name="test_step",
            objective="test objective",
            skills=["test-skill"],
            task_prompt="Generate something with {context}",
            validator=always_pass,
        )

        result = await execute_substep(
            substep=substep,
            state={"alert": "test alert"},
            store=store,
            llm=mock_llm,
        )

        assert result.output is not None
        assert result.attempts == 1
        assert len(result.validation_history) >= 1
        assert result.validation_history[-1].passed is True

    @pytest.mark.asyncio
    async def test_execute_deterministic(self, store: MockResourceStore, mock_llm):
        """SubStep with needs_context=False skips SkillsIR retrieval."""
        mock_llm.ainvoke = AsyncMock(return_value="Deterministic output")

        substep = SubStep(
            name="deterministic_step",
            objective="",  # Not used
            skills=[],
            task_prompt="Process {data}",
            validator=always_pass,
            needs_context=False,
        )

        result = await execute_substep(
            substep=substep,
            state={"data": "input data"},
            store=store,
            llm=mock_llm,
        )

        assert result.output is not None
        assert result.context is None  # No context retrieved
        # with_structured_output should NOT be called for deterministic steps
        # (no SkillsIR retrieval)

    @pytest.mark.asyncio
    async def test_execute_returns_context(self, store: MockResourceStore, mock_llm):
        """SubStepResult includes SkillContext used."""
        mock_llm.ainvoke = AsyncMock(return_value="Output with context")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        substep = SubStep(
            name="context_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Use {context}",
            validator=always_pass,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert result.context is not None
        assert "test-skill" in result.context.loaded


class TestExecuteSubstepRetryLogic:
    """Tests for retry logic in execute_substep."""

    @pytest.mark.asyncio
    async def test_execute_retry_on_failure(self, store: MockResourceStore, mock_llm):
        """SubStep retries when validation fails."""
        mock_llm.ainvoke = AsyncMock(return_value="Output")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        attempts = [0]
        substep = SubStep(
            name="retry_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Generate",
            validator=fail_then_pass(attempts),
            max_retries=5,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert result.validation_history[-1].passed is True
        assert result.attempts >= 2  # At least one retry

    @pytest.mark.asyncio
    async def test_execute_pass_after_retry(self, store: MockResourceStore, mock_llm):
        """SubStep passes after retry with corrected output."""
        # First output fails, second passes
        outputs = ["bad output", "good output"]
        mock_llm.ainvoke = AsyncMock(side_effect=outputs)
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        call_count = [0]

        def validator(output: str) -> ValidationResult:
            call_count[0] += 1
            if "bad" in output:
                return ValidationResult(passed=False, errors=["Bad output"])
            return ValidationResult(passed=True)

        substep = SubStep(
            name="retry_pass_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Generate",
            validator=validator,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert result.validation_history[-1].passed is True
        assert result.output == "good output"

    @pytest.mark.asyncio
    async def test_execute_max_retries_exceeded(
        self, store: MockResourceStore, mock_llm
    ):
        """Raises MaxRetriesExceededError after max_retries."""
        mock_llm.ainvoke = AsyncMock(return_value="Always bad output")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        substep = SubStep(
            name="fail_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Generate",
            validator=always_fail,
            max_retries=3,
        )

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await execute_substep(
                substep=substep,
                state={},
                store=store,
                llm=mock_llm,
            )

        assert exc_info.value.substep_name == "fail_step"
        assert exc_info.value.attempts == 3


class TestExecuteSubstepContextExpansion:
    """Tests for context expansion on needs_more_context."""

    @pytest.mark.asyncio
    async def test_execute_expands_context_on_hint(
        self, store: MockResourceStore, mock_llm
    ):
        """Re-retrieves with context_hint when needs_more_context=True."""
        mock_llm.ainvoke = AsyncMock(return_value="Output")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        call_count = [0]

        def validator(output: str) -> ValidationResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return ValidationResult(
                    passed=False,
                    errors=["Need more context"],
                    needs_more_context=True,
                    context_hint="load additional references",
                )
            return ValidationResult(passed=True)

        substep = SubStep(
            name="context_expand_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Generate",
            validator=validator,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert result.validation_history[-1].passed is True
        # Should have called SkillsIR twice (initial + expansion)


class TestExecuteSubstepValidationHistory:
    """Tests for validation history tracking."""

    @pytest.mark.asyncio
    async def test_execute_tracks_validation_history(
        self, store: MockResourceStore, mock_llm
    ):
        """SubStepResult.validation_history contains all attempts."""
        mock_llm.ainvoke = AsyncMock(return_value="Output")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        attempts = [0]
        substep = SubStep(
            name="history_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Generate",
            validator=fail_then_pass(attempts),
            max_retries=5,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert len(result.validation_history) >= 2
        # First attempts failed
        assert result.validation_history[0].passed is False
        # Last attempt passed
        assert result.validation_history[-1].passed is True

    @pytest.mark.asyncio
    async def test_execute_history_includes_errors(
        self, store: MockResourceStore, mock_llm
    ):
        """Failed validations include error messages in history."""
        mock_llm.ainvoke = AsyncMock(return_value="Output")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        call_count = [0]

        def validator(output: str) -> ValidationResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return ValidationResult(passed=False, errors=["Specific error message"])
            return ValidationResult(passed=True)

        substep = SubStep(
            name="error_history_step",
            objective="test",
            skills=["test-skill"],
            task_prompt="Generate",
            validator=validator,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert "Specific error message" in result.validation_history[0].errors


class TestExecuteSubstepEdgeCases:
    """Edge case tests for execute_substep."""

    @pytest.mark.asyncio
    async def test_execute_empty_skills_list(self, store: MockResourceStore, mock_llm):
        """SubStep with empty skills list works (minimal retrieval)."""
        mock_llm.ainvoke = AsyncMock(return_value="Output")
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = MagicMock(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        substep = SubStep(
            name="empty_skills_step",
            objective="test",
            skills=[],  # Empty skills list
            task_prompt="Generate without context",
            validator=always_pass,
        )

        result = await execute_substep(
            substep=substep,
            state={},
            store=store,
            llm=mock_llm,
        )

        assert result.output is not None
