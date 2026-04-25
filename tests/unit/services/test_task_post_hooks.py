"""Unit tests for Task Post-Completion Hooks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.task_post_hooks import (
    TaskMetadata,
    TaskPostHooks,
    create_task_post_hooks,
)


class TestTaskPostHooks:
    """Test suite for TaskPostHooks class."""

    @pytest.fixture
    def mock_llm_summarize(self):
        """Create a mock llm_summarize function."""
        return AsyncMock(return_value="IP Clean - Zero Malicious Indicators")

    @pytest.fixture
    def execution_context(self):
        """Create execution context."""
        return {
            "cy_name": "threat_analysis",
            "task_id": "test-task-id",
            "tenant_id": "test-tenant",
        }

    @pytest.fixture
    def task_metadata(self):
        """Create task metadata."""
        return TaskMetadata(
            name="Threat Analysis Task",
            description="Analyzes IPs for threat indicators",
            directive="You are a security analyst. Be concise and accurate.",
            cy_name="threat_analysis",
        )

    @pytest.fixture
    def post_hooks(self, mock_llm_summarize, execution_context):
        """Create TaskPostHooks instance."""
        return TaskPostHooks(
            llm_summarize_func=mock_llm_summarize,
            execution_context=execution_context,
        )

    @pytest.mark.asyncio
    async def test_generates_title_when_ai_analysis_present(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Auto-generates ai_analysis_title when ai_analysis exists in enrichments."""
        task_output = {
            "enrichments": {
                "threat_analysis": {
                    "score": 95,
                    "ai_analysis": "This IP shows 0 malicious indicators and 0 suspicious flags.",
                }
            }
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test Alert", "severity": "high"},
        )

        # Should have called LLM and added title
        mock_llm_summarize.assert_called_once()
        assert "ai_analysis_title" in result["enrichments"]["threat_analysis"]
        assert result["enrichments"]["threat_analysis"]["ai_analysis_title"] == (
            "IP Clean - Zero Malicious Indicators"
        )

    @pytest.mark.asyncio
    async def test_skips_when_no_ai_analysis(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Does not generate title when ai_analysis is missing."""
        task_output = {
            "enrichments": {
                "threat_analysis": {"score": 95}  # No ai_analysis
            }
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test Alert"},
        )

        mock_llm_summarize.assert_not_called()
        assert "ai_analysis_title" not in result["enrichments"]["threat_analysis"]

    @pytest.mark.asyncio
    async def test_skips_when_title_already_exists(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Does not overwrite existing ai_analysis_title."""
        task_output = {
            "enrichments": {
                "threat_analysis": {
                    "ai_analysis": "Some analysis text",
                    "ai_analysis_title": "Custom Title Already Set",
                }
            }
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test Alert"},
        )

        mock_llm_summarize.assert_not_called()
        assert result["enrichments"]["threat_analysis"]["ai_analysis_title"] == (
            "Custom Title Already Set"
        )

    @pytest.mark.asyncio
    async def test_skips_when_no_enrichments(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Handles output without enrichments dict."""
        task_output = {"result": "success"}

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test Alert"},
        )

        mock_llm_summarize.assert_not_called()
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_skips_when_non_dict_output(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Handles non-dict task output."""
        task_output = "just a string"

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test Alert"},
        )

        mock_llm_summarize.assert_not_called()
        assert result == "just a string"

    @pytest.mark.asyncio
    async def test_handles_llm_error_gracefully(self, task_metadata, execution_context):
        """Enrichment succeeds even if LLM call fails."""
        mock_llm = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context,
        )
        task_output = {
            "enrichments": {
                "threat_analysis": {
                    "ai_analysis": "Some analysis",
                    "score": 95,
                }
            }
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test Alert"},
        )

        # Output should be unchanged (no title added) but no error
        assert (
            result["enrichments"]["threat_analysis"]["ai_analysis"] == "Some analysis"
        )
        assert result["enrichments"]["threat_analysis"]["score"] == 95
        assert "ai_analysis_title" not in result["enrichments"]["threat_analysis"]

    @pytest.mark.asyncio
    async def test_uses_cy_name_from_context_if_not_in_metadata(
        self, mock_llm_summarize
    ):
        """Falls back to cy_name from execution_context if not in metadata."""
        execution_context = {"cy_name": "context_task"}
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm_summarize,
            execution_context=execution_context,
        )
        task_metadata = TaskMetadata(
            name="Task",
            description="A task",
            directive=None,
            cy_name=None,  # Not set in metadata
        )
        task_output = {
            "enrichments": {"context_task": {"ai_analysis": "Analysis text"}}
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test"},
        )

        mock_llm_summarize.assert_called_once()
        assert "ai_analysis_title" in result["enrichments"]["context_task"]

    @pytest.mark.asyncio
    async def test_builds_alert_context_from_original_input(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Alert context is built from original input."""
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "Analysis text"}}
        }
        original_input = {
            "title": "Suspicious Login Alert",
            "severity": "critical",
            "rule_name": "Failed Login Rule",
        }

        await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input=original_input,
        )

        # Check that llm_summarize was called with context containing alert info
        call_args = mock_llm_summarize.call_args
        context = call_args.kwargs.get("context")
        assert "Suspicious Login Alert" in context
        assert "critical" in context
        assert "Failed Login Rule" in context

    @pytest.mark.asyncio
    async def test_uses_task_directive_as_system_prompt(
        self, post_hooks, mock_llm_summarize
    ):
        """Task directive is passed to llm_summarize."""
        task_metadata = TaskMetadata(
            name="Task",
            description="A task",
            directive="Custom directive for this task",
            cy_name="threat_analysis",
        )
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "Analysis text"}}
        }

        await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test"},
        )

        call_args = mock_llm_summarize.call_args
        assert call_args.kwargs.get("directive") == "Custom directive for this task"

    @pytest.mark.asyncio
    async def test_truncates_long_ai_analysis(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Long ai_analysis is truncated before sending to LLM."""
        long_analysis = "x" * 5000  # Very long text
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": long_analysis}}
        }

        await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test"},
        )

        call_args = mock_llm_summarize.call_args
        text = call_args.kwargs.get("text")
        # Should be truncated to 2000 chars + "..."
        assert len(text) <= 2003

    @pytest.mark.asyncio
    async def test_handles_dict_ai_analysis(
        self, post_hooks, task_metadata, mock_llm_summarize
    ):
        """Handles ai_analysis that is a dict by JSON serializing it."""
        task_output = {
            "enrichments": {
                "threat_analysis": {
                    "ai_analysis": {
                        "verdict": "malicious",
                        "confidence": 0.95,
                        "reasoning": "Multiple indicators detected",
                    }
                }
            }
        }

        await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test"},
        )

        # LLM should have been called with JSON serialized analysis
        mock_llm_summarize.assert_called_once()
        call_args = mock_llm_summarize.call_args
        text = call_args.kwargs.get("text")
        assert "verdict" in text
        assert "malicious" in text

    @pytest.mark.asyncio
    async def test_strips_quotes_from_title(self, task_metadata, execution_context):
        """Strips quotes from LLM response."""
        mock_llm = AsyncMock(return_value='"Malicious IP Detected"')
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context,
        )
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "Some analysis"}}
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test"},
        )

        title = result["enrichments"]["threat_analysis"]["ai_analysis_title"]
        assert title == "Malicious IP Detected"
        assert '"' not in title

    @pytest.mark.asyncio
    async def test_truncates_long_titles(self, task_metadata, execution_context):
        """Truncates titles that are too long."""
        long_title = " ".join(["word"] * 30)  # 30 words
        mock_llm = AsyncMock(return_value=long_title)
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context,
        )
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "Some analysis"}}
        }

        result = await post_hooks.run_all_hooks(
            task_output=task_output,
            task_metadata=task_metadata,
            original_input={"title": "Test"},
        )

        title = result["enrichments"]["threat_analysis"]["ai_analysis_title"]
        # Should be truncated to ~20 words with ellipsis
        assert title.endswith("...")
        words = title.replace("...", "").split()
        assert len(words) <= 20


class TestArtifactCapture:
    """Test suite for AI Task Summarizer artifact capture."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        return MagicMock()

    @pytest.fixture
    def execution_context_with_session(self, mock_session):
        """Create execution context with session and IDs."""
        return {
            "cy_name": "threat_analysis",
            "task_id": "test-task-id",
            "tenant_id": "test-tenant",
            "session": mock_session,
            "task_run_id": "12345678-1234-5678-1234-567812345678",
            "analysis_id": "abcdefab-1234-5678-1234-567812345678",
        }

    @pytest.fixture
    def task_metadata(self):
        """Create task metadata."""
        return TaskMetadata(
            name="Threat Analysis Task",
            description="Analyzes IPs for threat indicators",
            directive="Be concise and accurate.",
            cy_name="threat_analysis",
        )

    @pytest.mark.asyncio
    async def test_captures_artifact_when_session_available(
        self, mock_session, execution_context_with_session, task_metadata
    ):
        """Artifact is captured when session is available."""
        mock_llm = AsyncMock(return_value="IP Clean - No Threats")
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context_with_session,
        )
        task_output = {
            "enrichments": {
                "threat_analysis": {"ai_analysis": "Analysis shows no threats."}
            }
        }

        with patch(
            "analysi.services.artifact_service.ArtifactService"
        ) as mock_artifact_svc_cls:
            mock_artifact_svc = MagicMock()
            mock_artifact_svc.create_artifact = AsyncMock()
            mock_artifact_svc_cls.return_value = mock_artifact_svc

            await post_hooks.run_all_hooks(
                task_output=task_output,
                task_metadata=task_metadata,
                original_input={"title": "Test Alert"},
            )

            # Verify artifact service was called
            mock_artifact_svc.create_artifact.assert_called_once()
            call_args = mock_artifact_svc.create_artifact.call_args

            # Check tenant_id
            assert call_args[0][0] == "test-tenant"

            # Check artifact data
            artifact_data = call_args[0][1]
            assert artifact_data.name == "AI Task Summarizer"
            assert artifact_data.artifact_type == "llm_summarization"
            assert artifact_data.source == "auto_capture"

    @pytest.mark.asyncio
    async def test_artifact_contains_prompt_and_completion(
        self, mock_session, execution_context_with_session, task_metadata
    ):
        """Artifact content includes prompt, completion, and duration."""
        mock_llm = AsyncMock(return_value="Malicious IP Detected")
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context_with_session,
        )
        task_output = {
            "enrichments": {
                "threat_analysis": {"ai_analysis": "This IP is flagged malicious."}
            }
        }

        with patch(
            "analysi.services.artifact_service.ArtifactService"
        ) as mock_artifact_svc_cls:
            mock_artifact_svc = MagicMock()
            mock_artifact_svc.create_artifact = AsyncMock()
            mock_artifact_svc_cls.return_value = mock_artifact_svc

            await post_hooks.run_all_hooks(
                task_output=task_output,
                task_metadata=task_metadata,
                original_input={"title": "Test Alert"},
            )

            # Parse the content JSON
            import json

            artifact_data = mock_artifact_svc.create_artifact.call_args[0][1]
            content = json.loads(artifact_data.content)

            assert "prompt" in content
            assert "completion" in content
            assert "duration_ms" in content
            assert "timestamp" in content
            assert content["completion"] == "Malicious IP Detected"
            assert "Threat Analysis Task" in content["prompt"]

    @pytest.mark.asyncio
    async def test_skips_artifact_when_no_session(self, task_metadata):
        """Artifact capture is skipped when no session."""
        execution_context = {
            "cy_name": "threat_analysis",
            "tenant_id": "test-tenant",
            # No session
        }
        mock_llm = AsyncMock(return_value="Clean IP")
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context,
        )
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "No threats."}}
        }

        with patch(
            "analysi.services.artifact_service.ArtifactService"
        ) as mock_artifact_svc_cls:
            await post_hooks.run_all_hooks(
                task_output=task_output,
                task_metadata=task_metadata,
                original_input={"title": "Test"},
            )

            # ArtifactService should not be instantiated
            mock_artifact_svc_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_artifact_when_no_tenant_id(self, mock_session, task_metadata):
        """Artifact capture is skipped when no tenant_id."""
        execution_context = {
            "cy_name": "threat_analysis",
            "session": mock_session,
            # No tenant_id
        }
        mock_llm = AsyncMock(return_value="Clean IP")
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context,
        )
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "No threats."}}
        }

        with patch(
            "analysi.services.artifact_service.ArtifactService"
        ) as mock_artifact_svc_cls:
            await post_hooks.run_all_hooks(
                task_output=task_output,
                task_metadata=task_metadata,
                original_input={"title": "Test"},
            )

            # ArtifactService should not be instantiated
            mock_artifact_svc_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_artifact_capture_failure_does_not_break_hook(
        self, mock_session, execution_context_with_session, task_metadata
    ):
        """Title generation succeeds even if artifact capture fails."""
        mock_llm = AsyncMock(return_value="Clean IP")
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context_with_session,
        )
        task_output = {
            "enrichments": {"threat_analysis": {"ai_analysis": "No threats detected."}}
        }

        with patch(
            "analysi.services.artifact_service.ArtifactService"
        ) as mock_artifact_svc_cls:
            mock_artifact_svc = MagicMock()
            mock_artifact_svc.create_artifact = AsyncMock(
                side_effect=RuntimeError("Database error")
            )
            mock_artifact_svc_cls.return_value = mock_artifact_svc

            result = await post_hooks.run_all_hooks(
                task_output=task_output,
                task_metadata=task_metadata,
                original_input={"title": "Test"},
            )

            # Title should still be generated despite artifact failure
            assert result["enrichments"]["threat_analysis"]["ai_analysis_title"] == (
                "Clean IP"
            )

    @pytest.mark.asyncio
    async def test_artifact_includes_execution_context_ids(
        self, mock_session, task_metadata
    ):
        """Artifact includes task_run_id, analysis_id from execution context."""
        from uuid import UUID

        execution_context = {
            "cy_name": "threat_analysis",
            "tenant_id": "test-tenant",
            "session": mock_session,
            "task_run_id": "12345678-1234-5678-1234-567812345678",
            "analysis_id": "abcdefab-1234-5678-1234-567812345678",
            "workflow_run_id": "11111111-2222-3333-4444-555555555555",
        }
        mock_llm = AsyncMock(return_value="Clean")
        post_hooks = TaskPostHooks(
            llm_summarize_func=mock_llm,
            execution_context=execution_context,
        )
        task_output = {"enrichments": {"threat_analysis": {"ai_analysis": "Clean."}}}

        with patch(
            "analysi.services.artifact_service.ArtifactService"
        ) as mock_artifact_svc_cls:
            mock_artifact_svc = MagicMock()
            mock_artifact_svc.create_artifact = AsyncMock()
            mock_artifact_svc_cls.return_value = mock_artifact_svc

            await post_hooks.run_all_hooks(
                task_output=task_output,
                task_metadata=task_metadata,
                original_input={"title": "Test"},
            )

            artifact_data = mock_artifact_svc.create_artifact.call_args[0][1]
            assert artifact_data.task_run_id == UUID(
                "12345678-1234-5678-1234-567812345678"
            )
            assert artifact_data.analysis_id == UUID(
                "abcdefab-1234-5678-1234-567812345678"
            )
            assert artifact_data.workflow_run_id == UUID(
                "11111111-2222-3333-4444-555555555555"
            )


class TestCreateTaskPostHooks:
    """Test factory function."""

    def test_returns_none_without_llm_summarize(self):
        """Factory returns None if llm_summarize not in functions dict."""
        llm_functions = {"llm_run": AsyncMock()}  # No llm_summarize
        execution_context = {"cy_name": "test"}

        result = create_task_post_hooks(llm_functions, execution_context)

        assert result is None

    def test_creates_hooks_with_llm_summarize(self):
        """Factory creates TaskPostHooks when llm_summarize is present."""
        llm_functions = {
            "llm_run": AsyncMock(),
            "llm_summarize": AsyncMock(),
        }
        execution_context = {"cy_name": "test"}

        result = create_task_post_hooks(llm_functions, execution_context)

        assert result is not None
        assert isinstance(result, TaskPostHooks)

    def test_returns_none_with_empty_functions(self):
        """Factory returns None with empty llm_functions dict."""
        result = create_task_post_hooks({}, {"cy_name": "test"})

        assert result is None


class TestTaskMetadata:
    """Test TaskMetadata dataclass."""

    def test_creates_with_all_fields(self):
        """Creates TaskMetadata with all fields."""
        metadata = TaskMetadata(
            name="Test Task",
            description="A test task",
            directive="Be helpful",
            cy_name="test_task",
        )

        assert metadata.name == "Test Task"
        assert metadata.description == "A test task"
        assert metadata.directive == "Be helpful"
        assert metadata.cy_name == "test_task"

    def test_allows_none_for_optional_fields(self):
        """Allows None for optional fields."""
        metadata = TaskMetadata(
            name="Test Task",
            description=None,
            directive=None,
            cy_name=None,
        )

        assert metadata.name == "Test Task"
        assert metadata.description is None
        assert metadata.directive is None
        assert metadata.cy_name is None
