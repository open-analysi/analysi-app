"""Tests for SkillContext and Pydantic models."""

from analysi.agentic_orchestration.langgraph.skills.context import (
    FileRequest,
    RetrievalDecision,
    SkillContext,
    estimate_tokens,
)


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_estimate_tokens_short_text(self):
        """Short text gets reasonable token count."""
        text = "Hello world"  # 11 chars
        tokens = estimate_tokens(text)
        assert tokens == 2  # 11 // 4 = 2

    def test_estimate_tokens_longer_text(self):
        """Longer text scales appropriately."""
        text = "This is a longer piece of text for testing."  # 43 chars
        tokens = estimate_tokens(text)
        assert tokens == 10  # 43 // 4 = 10

    def test_estimate_tokens_empty_string(self):
        """Empty string returns 0 tokens."""
        assert estimate_tokens("") == 0


class TestSkillContext:
    """Tests for SkillContext."""

    def test_initial_state(self):
        """New context starts empty with default limits."""
        context = SkillContext()

        assert context.registry == {}
        assert context.trees == {}
        assert context.loaded == {}
        assert context.token_count == 0
        assert context.token_limit == 50000

    def test_custom_token_limit(self):
        """Can set custom token limit."""
        context = SkillContext(token_limit=10000)
        assert context.token_limit == 10000

    def test_add_content_within_budget(self):
        """Adding content within budget succeeds."""
        context = SkillContext(token_limit=1000)

        success = context.add("skill-a", "file.md", "Short content")

        assert success is True
        assert "skill-a" in context.loaded
        assert context.loaded["skill-a"]["file.md"] == "Short content"
        assert context.token_count > 0

    def test_add_content_exceeds_budget(self):
        """Adding content that exceeds budget fails."""
        context = SkillContext(token_limit=10)  # Very small limit

        # This content has ~50 chars = ~12 tokens, exceeds limit of 10
        success = context.add("skill-a", "file.md", "x" * 50)

        assert success is False
        assert "skill-a" not in context.loaded
        assert context.token_count == 0

    def test_add_multiple_files_accumulates_tokens(self):
        """Multiple adds accumulate token count."""
        context = SkillContext(token_limit=1000)

        context.add("skill-a", "file1.md", "First content")
        first_count = context.token_count

        context.add("skill-a", "file2.md", "Second content")

        assert context.token_count > first_count
        assert len(context.loaded["skill-a"]) == 2

    def test_add_files_from_different_skills(self):
        """Can add files from multiple skills."""
        context = SkillContext(token_limit=1000)

        context.add("skill-a", "file.md", "Content A")
        context.add("skill-b", "file.md", "Content B")

        assert "skill-a" in context.loaded
        assert "skill-b" in context.loaded

    def test_for_prompt_empty_context(self):
        """for_prompt() returns empty string for empty context."""
        context = SkillContext()
        assert context.for_prompt() == ""

    def test_for_prompt_with_content(self):
        """for_prompt() formats content for LLM."""
        context = SkillContext()
        context.add("skill-a", "guide.md", "Guide content here")

        prompt = context.for_prompt()

        assert "### Skill: skill-a" in prompt
        assert "#### guide.md" in prompt
        assert "Guide content here" in prompt

    def test_for_prompt_multiple_skills(self):
        """for_prompt() includes all skills."""
        context = SkillContext()
        context.add("skill-a", "file.md", "Content A")
        context.add("skill-b", "file.md", "Content B")

        prompt = context.for_prompt()

        assert "skill-a" in prompt
        assert "skill-b" in prompt
        assert "Content A" in prompt
        assert "Content B" in prompt


class TestFileRequest:
    """Tests for FileRequest Pydantic model."""

    def test_create_file_request(self):
        """Can create FileRequest with required fields."""
        req = FileRequest(
            skill="runbooks-manager",
            path="references/guide.md",
            reason="Need composition guidance",
        )

        assert req.skill == "runbooks-manager"
        assert req.path == "references/guide.md"
        assert req.reason == "Need composition guidance"

    def test_file_request_to_dict(self):
        """FileRequest can be serialized to dict."""
        req = FileRequest(
            skill="skill-a",
            path="SKILL.md",
            reason="Initial context",
        )

        data = req.model_dump()

        assert data["skill"] == "skill-a"
        assert data["path"] == "SKILL.md"
        assert data["reason"] == "Initial context"


class TestRetrievalDecision:
    """Tests for RetrievalDecision Pydantic model."""

    def test_has_enough_true(self):
        """Can create decision indicating enough context."""
        decision = RetrievalDecision(has_enough=True)

        assert decision.has_enough is True
        assert decision.needs == []

    def test_has_enough_false_with_needs(self):
        """Can create decision requesting more files."""
        decision = RetrievalDecision(
            has_enough=False,
            needs=[
                FileRequest(
                    skill="skill-a",
                    path="file.md",
                    reason="Need this",
                )
            ],
        )

        assert decision.has_enough is False
        assert len(decision.needs) == 1
        assert decision.needs[0].skill == "skill-a"

    def test_retrieval_decision_from_dict(self):
        """RetrievalDecision can be created from dict (LLM output)."""
        data = {
            "has_enough": False,
            "needs": [
                {"skill": "skill-a", "path": "file.md", "reason": "reason"},
            ],
        }

        decision = RetrievalDecision.model_validate(data)

        assert decision.has_enough is False
        assert len(decision.needs) == 1
