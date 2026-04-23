"""Tests for SkillsIR retrieval with mocked LLM.

Uses MockResourceStore for tests (skills are now DB-only).
"""

import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration.langgraph.skills.context import (
    FileRequest,
    RetrievalDecision,
    SkillContext,
)
from analysi.agentic_orchestration.langgraph.skills.retrieval import (
    MAX_ITERATIONS,
    MAX_STRUCTURED_OUTPUT_RETRIES,
    init_node,
    load_files_node,
    make_check_enough_node,
    retrieve,
    should_continue,
)
from analysi.agentic_orchestration.langgraph.skills.store import (
    ResourceStore,
)


class MockResourceStore(ResourceStore):
    """Test-only ResourceStore that reads from filesystem.

    Used for unit tests since skills are now DB-only.
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir

    def list_skills(self) -> dict[str, str]:
        """List skills by scanning for directories with SKILL.md."""
        skills = {}
        if not self.skills_dir.exists():
            return skills
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    description = self._extract_description(skill_md)
                    skills[item.name] = description
        return skills

    def tree(self, skill: str) -> list[str]:
        """Get all file paths within a skill directory."""
        skill_dir = self.skills_dir / skill
        if not skill_dir.exists():
            return []
        paths = []
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(skill_dir)
                paths.append(str(relative_path))
        return sorted(paths)

    def read(self, skill: str, path: str) -> str | None:
        """Read file content from skill directory."""
        file_path = self.skills_dir / skill / path
        if not file_path.exists() or not file_path.is_file():
            return None
        return file_path.read_text()

    def _extract_description(self, skill_md_path: Path) -> str:
        """Extract description from SKILL.md YAML frontmatter."""
        content = skill_md_path.read_text()
        frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not frontmatter_match:
            return ""
        frontmatter = frontmatter_match.group(1)
        desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
        if desc_match:
            return desc_match.group(1).strip()
        return ""


@pytest.fixture
def temp_skills_dir() -> Path:
    """Create a temporary skills directory with test content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create skill-a
        skill_a = skills_dir / "skill-a"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(
            "---\n"
            "name: skill-a\n"
            "description: First test skill.\n"
            "---\n\n"
            "# Skill A Content"
        )
        (skill_a / "references").mkdir()
        (skill_a / "references" / "guide.md").write_text("# Guide\nDetailed guidance.")
        (skill_a / "references" / "examples.md").write_text(
            "# Examples\nSome examples."
        )

        # Create skill-b
        skill_b = skills_dir / "skill-b"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text(
            "---\n"
            "name: skill-b\n"
            "description: Second test skill.\n"
            "---\n\n"
            "# Skill B Content"
        )

        yield skills_dir


@pytest.fixture
def temp_skills_with_wikilinks() -> Path:
    """Create skills directory with WikiLink references."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create skill with WikiLinks (like runbooks-manager)
        skill = skills_dir / "runbooks"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\n"
            "name: runbooks\n"
            "description: Runbook skill with WikiLinks.\n"
            "---\n\n"
            "# Runbooks Skill"
        )

        # Create common/ with reusable content
        common = skill / "common"
        common.mkdir()
        (common / "header.md").write_text(
            "## Standard Investigation Header\nAlways start with these steps."
        )
        (common / "evidence.md").write_text(
            "## Evidence Collection\nCollect logs from SIEM."
        )

        # Create repository/ with runbooks that use WikiLinks
        repository = skill / "repository"
        repository.mkdir()
        (repository / "sql-injection.md").write_text(
            "# SQL Injection Runbook\n\n"
            "![[common/header.md]]\n\n"
            "## SQL-Specific Steps\n"
            "Check for injection patterns.\n\n"
            "![[common/evidence.md]]"
        )

        yield skills_dir


@pytest.fixture
def store(temp_skills_dir: Path) -> MockResourceStore:
    """Create store from temp directory."""
    return MockResourceStore(temp_skills_dir)


class TestInitNode:
    """Tests for init_node."""

    @pytest.mark.asyncio
    async def test_loads_registry(self, store: MockResourceStore):
        """init_node loads skill registry."""
        state = {
            "store": store,
            "initial_skills": ["skill-a"],
            "objective": "test",
            "task_input": "{}",
        }

        result = await init_node(state)

        context = result["context"]
        assert "skill-a" in context.registry
        assert "skill-b" in context.registry

    @pytest.mark.asyncio
    async def test_loads_trees_for_initial_skills(self, store: MockResourceStore):
        """init_node loads file trees for initial skills only."""
        state = {
            "store": store,
            "initial_skills": ["skill-a"],
            "objective": "test",
            "task_input": "{}",
        }

        result = await init_node(state)

        context = result["context"]
        assert "skill-a" in context.trees
        assert "skill-b" not in context.trees

    @pytest.mark.asyncio
    async def test_loads_skill_md(self, store: MockResourceStore):
        """init_node loads SKILL.md for initial skills."""
        state = {
            "store": store,
            "initial_skills": ["skill-a"],
            "objective": "test",
            "task_input": "{}",
        }

        result = await init_node(state)

        context = result["context"]
        assert "skill-a" in context.loaded
        assert "SKILL.md" in context.loaded["skill-a"]
        assert "# Skill A Content" in context.loaded["skill-a"]["SKILL.md"]


class TestLoadFilesNode:
    """Tests for load_files_node."""

    @pytest.mark.asyncio
    async def test_loads_requested_files(self, store: MockResourceStore):
        """load_files_node loads files from decision.needs."""
        context = SkillContext()
        decision = RetrievalDecision(
            has_enough=False,
            needs=[
                FileRequest(skill="skill-a", path="references/guide.md", reason="test"),
            ],
        )

        state = {
            "store": store,
            "context": context,
            "decision": decision,
        }

        result = await load_files_node(state)

        updated_context = result["context"]
        assert "skill-a" in updated_context.loaded
        assert "references/guide.md" in updated_context.loaded["skill-a"]

    @pytest.mark.asyncio
    async def test_respects_max_files_limit(self, store: MockResourceStore):
        """load_files_node only loads MAX_FILES_PER_REQUEST files."""
        context = SkillContext()
        # Request more files than allowed
        decision = RetrievalDecision(
            has_enough=False,
            needs=[
                FileRequest(skill="skill-a", path=f"file{i}.md", reason="test")
                for i in range(10)
            ],
        )

        state = {
            "store": store,
            "context": context,
            "decision": decision,
        }

        await load_files_node(state)

        # Should not have loaded more than MAX_FILES_PER_REQUEST
        # (files don't exist, so nothing loaded, but no error)

    @pytest.mark.asyncio
    async def test_noop_when_has_enough(self, store: MockResourceStore):
        """load_files_node does nothing when has_enough=True."""
        context = SkillContext()
        decision = RetrievalDecision(has_enough=True)

        state = {
            "store": store,
            "context": context,
            "decision": decision,
        }

        result = await load_files_node(state)

        assert result == {}


class TestShouldContinue:
    """Tests for should_continue routing function."""

    def test_finish_when_has_enough(self):
        """Returns 'finish' when LLM says it has enough."""
        state = {
            "decision": RetrievalDecision(has_enough=True),
            "iteration": 1,
        }

        assert should_continue(state) == "finish"

    def test_continue_when_needs_files(self):
        """Returns 'check_enough' when LLM needs more files."""
        state = {
            "decision": RetrievalDecision(
                has_enough=False,
                needs=[FileRequest(skill="s", path="p", reason="r")],
            ),
            "iteration": 1,
        }

        assert should_continue(state) == "check_enough"

    def test_finish_at_max_iterations(self):
        """Returns 'finish' when max iterations reached."""
        state = {
            "decision": RetrievalDecision(
                has_enough=False,
                needs=[FileRequest(skill="s", path="p", reason="r")],
            ),
            "iteration": MAX_ITERATIONS,
        }

        assert should_continue(state) == "finish"

    def test_check_enough_on_first_iteration(self):
        """Returns 'check_enough' on first iteration."""
        state = {
            "decision": None,
            "iteration": 0,
        }

        assert should_continue(state) == "check_enough"


class TestRetrieveIntegration:
    """Integration tests for retrieve() with mocked LLM."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM that returns predetermined decisions."""
        mock = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_retrieve_immediate_success(self, store: MockResourceStore, mock_llm):
        """retrieve() completes when LLM says has_enough immediately."""
        # Mock LLM to say "has enough" immediately
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = RetrievalDecision(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        context = await retrieve(
            store=store,
            initial_skills=["skill-a"],
            task_input={"alert": "test"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        assert context.token_count > 0  # SKILL.md was loaded
        assert "skill-a" in context.loaded
        mock_structured.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_with_one_iteration(
        self, store: MockResourceStore, mock_llm
    ):
        """retrieve() loads additional files when LLM requests them."""
        # First call: need more files
        # Second call: has enough
        decisions = [
            RetrievalDecision(
                has_enough=False,
                needs=[
                    FileRequest(
                        skill="skill-a",
                        path="references/guide.md",
                        reason="Need guidance",
                    )
                ],
            ),
            RetrievalDecision(has_enough=True),
        ]

        mock_structured = AsyncMock()
        mock_structured.ainvoke.side_effect = decisions
        mock_llm.with_structured_output.return_value = mock_structured

        context = await retrieve(
            store=store,
            initial_skills=["skill-a"],
            task_input={"alert": "test"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        # Should have loaded SKILL.md + guide.md
        assert "SKILL.md" in context.loaded["skill-a"]
        assert "references/guide.md" in context.loaded["skill-a"]
        assert mock_structured.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_retrieve_respects_max_iterations(
        self, store: MockResourceStore, mock_llm
    ):
        """retrieve() stops at MAX_ITERATIONS even if LLM keeps requesting."""
        # Always request more files
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = RetrievalDecision(
            has_enough=False,
            needs=[
                FileRequest(
                    skill="skill-a",
                    path="nonexistent.md",
                    reason="Keep going",
                )
            ],
        )
        mock_llm.with_structured_output.return_value = mock_structured

        await retrieve(
            store=store,
            initial_skills=["skill-a"],
            task_input={"alert": "test"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        # Should have called LLM MAX_ITERATIONS times
        assert mock_structured.ainvoke.call_count == MAX_ITERATIONS


class TestWikiLinkExpansionInRetrieval:
    """Tests for WikiLink expansion during retrieval."""

    @pytest.fixture
    def wikilink_store(self, temp_skills_with_wikilinks: Path) -> MockResourceStore:
        """Create store with WikiLink-enabled skills."""
        return MockResourceStore(temp_skills_with_wikilinks)

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_load_files_expands_wikilinks(
        self, wikilink_store: MockResourceStore
    ):
        """load_files_node expands WikiLinks when loading files."""
        context = SkillContext()
        decision = RetrievalDecision(
            has_enough=False,
            needs=[
                FileRequest(
                    skill="runbooks",
                    path="repository/sql-injection.md",
                    reason="Need runbook",
                ),
            ],
        )

        state = {
            "store": wikilink_store,
            "context": context,
            "decision": decision,
            "iteration": 1,
        }

        result = await load_files_node(state)

        updated_context = result["context"]
        loaded_content = updated_context.loaded["runbooks"][
            "repository/sql-injection.md"
        ]

        # WikiLinks should be expanded inline
        assert "![[" not in loaded_content, "WikiLinks should be expanded"

        # Content from WikiLinked files should be present
        assert "## Standard Investigation Header" in loaded_content
        assert "Always start with these steps" in loaded_content
        assert "## Evidence Collection" in loaded_content
        assert "Collect logs from SIEM" in loaded_content

        # Original content should still be there
        assert "# SQL Injection Runbook" in loaded_content
        assert "## SQL-Specific Steps" in loaded_content

    @pytest.mark.asyncio
    async def test_retrieve_with_wikilink_expansion(
        self, wikilink_store: MockResourceStore, mock_llm
    ):
        """Full retrieve() flow expands WikiLinks in loaded files."""
        # LLM requests runbook, then says has enough
        decisions = [
            RetrievalDecision(
                has_enough=False,
                needs=[
                    FileRequest(
                        skill="runbooks",
                        path="repository/sql-injection.md",
                        reason="Need investigation runbook",
                    )
                ],
            ),
            RetrievalDecision(has_enough=True),
        ]

        mock_structured = AsyncMock()
        mock_structured.ainvoke.side_effect = decisions
        mock_llm.with_structured_output.return_value = mock_structured

        context = await retrieve(
            store=wikilink_store,
            initial_skills=["runbooks"],
            task_input={"alert": "SQL injection detected"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        # Runbook should be loaded with WikiLinks expanded
        runbook_content = context.loaded["runbooks"]["repository/sql-injection.md"]
        assert "![[" not in runbook_content, "WikiLinks should be expanded"
        assert "## Standard Investigation Header" in runbook_content
        assert "## Evidence Collection" in runbook_content


class TestCheckEnoughNodeRetry:
    """Tests for retry + fallback in check_enough_node."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """check_enough_node returns decision when LLM succeeds immediately."""
        mock_llm = MagicMock()
        mock_structured = AsyncMock()
        mock_structured.ainvoke.return_value = RetrievalDecision(has_enough=True)
        mock_llm.with_structured_output.return_value = mock_structured

        node_fn = make_check_enough_node(mock_llm)
        state = {
            "context": SkillContext(),
            "objective": "test",
            "task_input": "{}",
            "iteration": 0,
        }

        result = await node_fn(state)

        assert result["decision"].has_enough is True
        assert mock_structured.ainvoke.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_validation_error(self):
        """check_enough_node retries when LLM returns invalid output."""
        mock_llm = MagicMock()
        mock_structured = AsyncMock()
        # First call raises, second succeeds
        mock_structured.ainvoke.side_effect = [
            ValueError("Invalid output"),
            RetrievalDecision(
                has_enough=False,
                needs=[
                    FileRequest(skill="s", path="p.md", reason="r"),
                ],
            ),
        ]
        mock_llm.with_structured_output.return_value = mock_structured

        node_fn = make_check_enough_node(mock_llm)
        state = {
            "context": SkillContext(),
            "objective": "test",
            "task_input": "{}",
            "iteration": 0,
        }

        result = await node_fn(state)

        assert result["decision"].has_enough is False
        assert len(result["decision"].needs) == 1
        assert mock_structured.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_falls_back_when_all_retries_fail(self):
        """check_enough_node returns safe default when all retries exhausted."""
        mock_llm = MagicMock()
        mock_structured = AsyncMock()
        mock_structured.ainvoke.side_effect = ValueError("Always fails")
        mock_llm.with_structured_output.return_value = mock_structured

        node_fn = make_check_enough_node(mock_llm)
        state = {
            "context": SkillContext(),
            "objective": "test",
            "task_input": "{}",
            "iteration": 0,
        }

        result = await node_fn(state)

        # Safe fallback: has_enough=True (use whatever context we have)
        assert result["decision"].has_enough is True
        assert result["decision"].needs == []
        assert mock_structured.ainvoke.call_count == MAX_STRUCTURED_OUTPUT_RETRIES

    @pytest.mark.asyncio
    async def test_full_retrieve_survives_flaky_llm(self, store: MockResourceStore):
        """retrieve() completes even when LLM is flaky on structured output."""
        mock_llm = MagicMock()
        mock_structured = AsyncMock()
        # First attempt fails, retry succeeds with has_enough=True
        mock_structured.ainvoke.side_effect = [
            ValueError("Bad output"),
            RetrievalDecision(has_enough=True),
        ]
        mock_llm.with_structured_output.return_value = mock_structured

        context = await retrieve(
            store=store,
            initial_skills=["skill-a"],
            task_input={"alert": "test"},
            objective="Match alert to runbook",
            llm=mock_llm,
        )

        assert context.token_count > 0
        assert "skill-a" in context.loaded
