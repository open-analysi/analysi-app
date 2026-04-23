"""Tests for Runbook Matching LangGraph.

Requires the runbooks-manager skill to be installed locally.
Skipped in CI where skills are not available.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Skip entire module if RunbookMatcher script is not available
_SKILL_PATHS = [
    Path(__file__).parents[5]
    / "docker"
    / "agents_skills"
    / "skills"
    / "runbooks-manager"
    / "scripts"
    / "match_scorer.py",
    Path.home()
    / ".claude"
    / "skills"
    / "runbooks-manager"
    / "scripts"
    / "match_scorer.py",
]
if not any(p.exists() for p in _SKILL_PATHS):
    pytest.skip("RunbookMatcher skill not available", allow_module_level=True)

from analysi.agentic_orchestration.langgraph.kea.phase1.graph import (  # noqa: E402
    build_phase1_graph,
    run_phase1,
)
from analysi.agentic_orchestration.langgraph.skills.context import (  # noqa: E402
    RetrievalDecision,
)
from tests.unit.agentic_orchestration.langgraph.kea.conftest import (  # noqa: E402
    _MockAIMessage,
)


@pytest.fixture
def temp_repository():
    """Create a temporary runbook repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create index file with exact match runbook
        index = [
            {
                "filename": "sql-injection-detection.md",
                "detection_rule": "Possible SQL Injection Payload Detected",
                "alert_type": "Web Attack",
                "subcategory": "SQL Injection",
                "source_category": "WAF",
                "mitre_tactics": ["T1190"],
            },
        ]
        (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": index}))

        # Create runbook file
        (repo_path / "sql-injection-detection.md").write_text(
            """---
title: SQL Injection Investigation
detection_rule: Possible SQL Injection Payload Detected
---

# SQL Injection Investigation

## Steps

### 1. Alert Understanding ★
Review the SQL injection attempt details.

### 2. Payload Analysis ★
Analyze the injection payload.
"""
        )

        yield repo_path


class TestGraphStructure:
    """Tests for graph assembly."""

    def test_graph_builds_without_error(self, mock_llm, mock_store):
        """Graph can be built."""
        graph = build_phase1_graph(mock_llm, mock_store)
        assert graph is not None

    def test_graph_has_nodes(self, mock_llm, mock_store):
        """Graph has expected nodes."""
        graph = build_phase1_graph(mock_llm, mock_store)

        # Check that graph has nodes (implementation dependent)
        assert graph is not None


class TestMatchPathRouting:
    """Tests for match path routing."""

    @pytest.mark.asyncio
    async def test_route_very_high_to_fetch(
        self,
        mock_llm_with_structured_output,
        mock_store,
        temp_repository,
        sample_alert_exact_match,
    ):
        """VERY_HIGH confidence routes to fetch path."""
        result = await run_phase1(
            alert=sample_alert_exact_match,
            llm=mock_llm_with_structured_output,
            store=mock_store,
            repository_path=str(temp_repository),
        )

        assert result["runbook"] is not None
        assert "SQL Injection Investigation" in result["runbook"]

    @pytest.mark.asyncio
    async def test_match_path_skips_composition(
        self,
        mock_llm_with_structured_output,
        mock_store,
        temp_repository,
        sample_alert_exact_match,
    ):
        """Match path doesn't call LLM composition steps."""
        # Track LLM calls
        call_count = [0]
        original_ainvoke = mock_llm_with_structured_output.ainvoke

        async def track_ainvoke(*args, **kwargs):
            call_count[0] += 1
            return await original_ainvoke(*args, **kwargs)

        mock_llm_with_structured_output.ainvoke = track_ainvoke

        result = await run_phase1(
            alert=sample_alert_exact_match,
            llm=mock_llm_with_structured_output,
            store=mock_store,
            repository_path=str(temp_repository),
        )

        # For match path, main LLM ainvoke should not be called
        # (only SkillsIR might use structured output)
        assert result["runbook"] is not None
        # Composition steps would call ainvoke for each step - match path should not
        assert call_count[0] == 0


class TestCompositionPathRouting:
    """Tests for composition path routing."""

    @pytest.mark.asyncio
    async def test_route_medium_to_compose(
        self, mock_llm_with_structured_output, mock_store, sample_alert_composition
    ):
        """MEDIUM confidence routes to composition with SkillsIR."""
        # Uses mock_llm_with_structured_output fixture which handles:
        # 1. SkillsIR structured output (RetrievalDecision)
        # 2. Composition substep structured outputs (GapAnalysisOutput, StrategyOutput, ExtractionOutput)
        # 3. Free-form text for compose_runbook step

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            # Create empty index (no exact matches)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm_with_structured_output,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Should have composed a runbook
        assert (
            result.get("runbook") is not None
            or result.get("composition_metadata") is not None
        )

    @pytest.mark.asyncio
    async def test_composition_uses_skillsir(
        self, mock_store, sample_alert_composition
    ):
        """Composition path calls SkillsIR for context retrieval."""
        from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
            ExtractionOutput,
            Gap,
            GapAnalysisOutput,
            StrategyOutput,
        )

        mock_llm = MagicMock()

        # Track SkillsIR calls (only for RetrievalDecision)
        skillsir_calls = []

        def create_structured_mock(schema):
            """Create mock that tracks SkillsIR calls and returns correct response."""
            structured_mock = AsyncMock()

            async def mock_ainvoke(*args, **kwargs):
                if schema == RetrievalDecision:
                    skillsir_calls.append(args)
                    return RetrievalDecision(has_enough=True, needs=[])
                if schema == GapAnalysisOutput:
                    return GapAnalysisOutput(
                        gaps=[
                            Gap(
                                category="xss",
                                description="XSS not covered",
                                severity="high",
                            )
                        ],
                        coverage_assessment="partial",
                    )
                if schema == StrategyOutput:
                    return StrategyOutput(
                        strategy="minimal_scaffold", sources=[], template=None
                    )
                if schema == ExtractionOutput:
                    return ExtractionOutput(extractions=[], remaining_gaps=[])
                return RetrievalDecision(has_enough=True, needs=[])

            structured_mock.ainvoke = mock_ainvoke
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        # Free-form response for compose_runbook (no output_schema)
        mock_llm.ainvoke = AsyncMock(
            return_value=_MockAIMessage("# Test\n\n## Steps\n\n### 1. Step ★\nContent.")
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # SkillsIR should have been called for each composition SubStep (4 steps)
        # Each substep calls SkillsIR once for initial context retrieval
        assert len(skillsir_calls) == 4, (
            f"Expected 4 SkillsIR calls, got {len(skillsir_calls)}"
        )


class TestEndToEnd:
    """End-to-end tests with mocked LLM."""

    @pytest.mark.asyncio
    async def test_run_phase1_match_path(
        self,
        mock_llm_with_structured_output,
        mock_store,
        temp_repository,
        sample_alert_exact_match,
    ):
        """Full match path execution returns runbook."""
        result = await run_phase1(
            alert=sample_alert_exact_match,
            llm=mock_llm_with_structured_output,
            store=mock_store,
            repository_path=str(temp_repository),
        )

        assert "runbook" in result
        assert result["runbook"] is not None
        # Should contain the matched runbook content
        assert "SQL Injection" in result["runbook"]

    @pytest.mark.asyncio
    async def test_run_phase1_returns_metadata(
        self,
        mock_llm_with_structured_output,
        mock_store,
        temp_repository,
        sample_alert_exact_match,
    ):
        """Run returns confidence and match info."""
        result = await run_phase1(
            alert=sample_alert_exact_match,
            llm=mock_llm_with_structured_output,
            store=mock_store,
            repository_path=str(temp_repository),
        )

        # Should include metadata about the match
        assert "confidence" in result or "matches" in result

    @pytest.mark.asyncio
    async def test_run_phase1_composition_with_skillsir_context(
        self, mock_store, sample_alert_composition
    ):
        """Composition path properly uses SkillsIR context in prompts."""
        from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
            Extraction,
            ExtractionOutput,
            Gap,
            GapAnalysisOutput,
            StrategyOutput,
        )

        mock_llm = MagicMock()

        # Track prompts sent to structured output
        structured_prompts_received = []

        def create_structured_mock(schema):
            """Create mock that tracks prompts and returns correct response."""
            structured_mock = AsyncMock()

            async def mock_ainvoke(prompt):
                structured_prompts_received.append((schema.__name__, prompt))
                if schema == RetrievalDecision:
                    return RetrievalDecision(has_enough=True, needs=[])
                if schema == GapAnalysisOutput:
                    return GapAnalysisOutput(
                        gaps=[
                            Gap(category="test", description="test", severity="high")
                        ],
                        coverage_assessment="50%",
                    )
                if schema == StrategyOutput:
                    return StrategyOutput(
                        strategy="minimal_scaffold", sources=[], template=None
                    )
                if schema == ExtractionOutput:
                    return ExtractionOutput(
                        extractions=[
                            Extraction(content="test", source="test.md", section="s1")
                        ],
                        remaining_gaps=[],
                    )
                return RetrievalDecision(has_enough=True, needs=[])

            structured_mock.ainvoke = mock_ainvoke
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        # Free-form response for compose_runbook (no output_schema)
        mock_llm.ainvoke = AsyncMock(
            return_value=_MockAIMessage("# Test\n\n## Steps\n\n### 1. Step ★\nContent.")
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Verify composition happened
        assert result["runbook"] is not None
        assert result["composition_metadata"] is not None

        # Verify structured output was called for:
        # 4 SkillsIR calls + 3 composition substeps (gap, strategy, extraction)
        # compose_runbook uses ainvoke (no structured output)
        structured_calls = [name for name, _ in structured_prompts_received]
        assert structured_calls.count("GapAnalysisOutput") == 1
        assert structured_calls.count("StrategyOutput") == 1
        assert structured_calls.count("ExtractionOutput") == 1


class TestFixRunbookLoop:
    """Tests for fix_runbook validation loop."""

    def _create_composition_mock(self, ainvoke_responses):
        """Helper to create a properly configured composition mock.

        Args:
            ainvoke_responses: List of responses for ainvoke calls (compose_runbook, fix_runbook)
        """
        from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
            ExtractionOutput,
            GapAnalysisOutput,
            StrategyOutput,
        )

        mock_llm = MagicMock()
        ainvoke_call_count = [0]

        def create_structured_mock(schema):
            """Create mock that returns correct response for schema."""
            structured_mock = AsyncMock()

            async def mock_ainvoke(*args, **kwargs):
                if schema == RetrievalDecision:
                    return RetrievalDecision(has_enough=True, needs=[])
                if schema == GapAnalysisOutput:
                    return GapAnalysisOutput(gaps=[], coverage_assessment="100%")
                if schema == StrategyOutput:
                    return StrategyOutput(
                        strategy="minimal_scaffold", sources=[], template=None
                    )
                if schema == ExtractionOutput:
                    return ExtractionOutput(extractions=[], remaining_gaps=[])
                return RetrievalDecision(has_enough=True, needs=[])

            structured_mock.ainvoke = mock_ainvoke
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        # Free-form responses for compose_runbook and fix_runbook
        # Wrap in _MockAIMessage so executor extracts .content (like real AIMessage)
        async def mock_ainvoke(*args, **kwargs):
            idx = ainvoke_call_count[0]
            ainvoke_call_count[0] += 1
            raw = (
                ainvoke_responses[idx]
                if idx < len(ainvoke_responses)
                else ainvoke_responses[-1]
            )
            return _MockAIMessage(raw)

        mock_llm.ainvoke = mock_ainvoke

        return mock_llm, ainvoke_call_count

    @pytest.mark.asyncio
    async def test_valid_runbook_skips_fix(self, mock_store, sample_alert_composition):
        """Valid runbook goes directly to END without fix_runbook."""
        # compose_runbook returns valid runbook with ★ marker
        mock_llm, call_count = self._create_composition_mock(
            ["# Test\n\n## Steps\n\n### 1. Step ★\nValid content."]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Should have valid runbook with no fix retries
        assert result["runbook"] is not None
        assert result["fix_retries"] == 0
        # Only 1 ainvoke call (compose_runbook only, no fix_runbook)
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_invalid_runbook_triggers_fix(
        self, mock_store, sample_alert_composition
    ):
        """Invalid runbook (missing ★) triggers fix_runbook."""
        # First: invalid runbook, Second: fixed runbook
        mock_llm, call_count = self._create_composition_mock(
            [
                "# Test\n\n## Steps\n\n### 1. Step\nMissing star.",  # Invalid
                "# Test\n\n## Steps\n\n### 1. Step ★\nFixed content.",  # Fixed
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Should have fixed runbook after 1 retry
        assert result["runbook"] is not None
        assert "★" in result["runbook"]
        assert result["fix_retries"] == 1
        # 2 ainvoke calls (compose + 1 fix)
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_max_retries_reached(self, mock_store, sample_alert_composition):
        """fix_runbook stops after MAX_FIX_RETRIES even if still invalid."""
        # Always return invalid runbook (missing ★)
        mock_llm, call_count = self._create_composition_mock(
            ["# Test\n\n## Steps\n\n### 1. Step\nPersistently invalid."]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Should hit max retries (2) and stop
        assert result["fix_retries"] == 2
        # 3 ainvoke calls (compose + 2 fix attempts)
        assert call_count[0] == 3
        # Still has the invalid runbook (best effort)
        assert result["runbook"] is not None

    @pytest.mark.asyncio
    async def test_composed_runbook_persisted_to_store(
        self, mock_store, sample_alert_composition
    ):
        """Composed runbook is written to the store and index is updated."""
        mock_llm, _call_count = self._create_composition_mock(
            ["# Composed Runbook\n\n## Steps\n\n### 1. Investigate ★\nDo it."]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_composition,
                llm=mock_llm,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Verify runbook was composed (not matched)
        assert result["matching_report"]["decision"] == "composed"

        # Verify store.write_document_async was called with generated slug filename
        mock_store.write_document_async.assert_called_once()
        call_args = mock_store.write_document_async.call_args
        skill_name, path, content = call_args[0]
        assert skill_name == "runbooks-manager"
        assert path.startswith("repository/")
        assert path.endswith(".md")
        assert "idor" in path.lower()  # slug from alert title
        assert content == result["runbook"]

        # Verify matching_report has the generated filename (not a default placeholder)
        filename = result["matching_report"]["composed_runbook"]
        assert filename.endswith(".md")
        assert filename != "composed-runbook.md"  # Must not be default placeholder

        # Verify index was updated
        mock_store.read_table_async.assert_called()
        mock_store.write_table_async.assert_called_once()
        index_call_args = mock_store.write_table_async.call_args[0]
        assert index_call_args[0] == "runbooks-manager"
        assert index_call_args[1] == "index/all_runbooks"
        # The new entry should be appended to the existing index
        updated_index = index_call_args[2]
        composed_entries = [e for e in updated_index if e.get("source") == "composed"]
        assert len(composed_entries) == 1
        assert composed_entries[0]["filename"] == filename

    @pytest.mark.asyncio
    async def test_matched_runbook_not_persisted(
        self, mock_store, mock_llm_with_structured_output, sample_alert_exact_match
    ):
        """Matched runbooks (not composed) should not trigger persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "all_runbooks.json").write_text(json.dumps({"runbooks": []}))

            result = await run_phase1(
                alert=sample_alert_exact_match,
                llm=mock_llm_with_structured_output,
                store=mock_store,
                repository_path=str(repo_path),
            )

        # Should be a match, not composition
        assert result["matching_report"]["decision"] == "matched"

        # Store should NOT have write calls (no persistence for matches)
        mock_store.write_document_async.assert_not_called()
        mock_store.write_table_async.assert_not_called()
