"""
Unit tests for directive injection as system prompt in llm_run.

When a task has a directive, all llm_run calls within that task should
pass the directive as a `context` parameter to the framework's LlmRunAction,
which uses it as a system message in the API call.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.services.cy_llm_functions import CyLLMFunctions


def _make_framework_result(response_text: str = "LLM response") -> dict:
    """Build a standard framework action success result."""
    return {
        "status": "success",
        "data": {
            "response": response_text,
            "message": {"role": "assistant", "content": response_text},
            "input_tokens": 10,
            "output_tokens": 5,
        },
    }


def _make_mock_service(
    response_text: str = "LLM response",
) -> AsyncMock:
    """Create a mock IntegrationService with execute_action + list_integrations."""
    mock_svc = AsyncMock()

    # list_integrations returns one AI integration for primary resolution
    mock_integration = MagicMock()
    mock_integration.integration_id = "anthropic-agent-main"
    mock_integration.integration_type = "anthropic_agent"
    mock_integration.settings = {"is_primary": True}
    mock_svc.list_integrations.return_value = [mock_integration]

    # get_integration for by-ID lookup
    mock_svc.get_integration.return_value = mock_integration

    # execute_action returns a framework result
    mock_svc.execute_action.return_value = _make_framework_result(response_text)

    return mock_svc


@pytest.mark.unit
class TestDirectiveAsSystemPrompt:
    """Test that task directive is passed as context to framework actions."""

    @pytest.fixture
    def mock_service(self):
        """Create a mock IntegrationService."""
        return _make_mock_service()

    @pytest.fixture
    def context_with_directive(self):
        """Execution context that includes a task directive."""
        return {
            "tenant_id": "test-tenant",
            "task_run_id": str(uuid.uuid4()),
            "session": MagicMock(),
            "directive": "You are a senior security analyst. Be concise.",
        }

    @pytest.fixture
    def context_without_directive(self):
        """Execution context without a directive."""
        return {
            "tenant_id": "test-tenant",
            "task_run_id": str(uuid.uuid4()),
            "session": MagicMock(),
        }

    @pytest.mark.asyncio
    async def test_llm_run_passes_context_when_directive_present(
        self, mock_service, context_with_directive
    ):
        """When directive is in execution_context, execute_action receives
        context=directive in params."""
        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_run(prompt="Analyze this alert")

        # Verify execute_action was called with context param
        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert params["prompt"] == "Analyze this alert"
        assert params["context"] == "You are a senior security analyst. Be concise."

    @pytest.mark.asyncio
    async def test_llm_run_no_context_when_no_directive(
        self, mock_service, context_without_directive
    ):
        """When no directive, context should not be in params."""
        cy_llm = CyLLMFunctions(mock_service, context_without_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_run(prompt="Analyze this alert")

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert params["prompt"] == "Analyze this alert"
        assert "context" not in params

    @pytest.mark.asyncio
    async def test_llm_run_directive_empty_string_treated_as_no_directive(
        self, mock_service
    ):
        """Empty directive string should behave same as no directive."""
        context = {
            "tenant_id": "test-tenant",
            "task_run_id": str(uuid.uuid4()),
            "session": MagicMock(),
            "directive": "",
        }

        cy_llm = CyLLMFunctions(mock_service, context)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_run(prompt="Test prompt")

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert "context" not in params

    @pytest.mark.asyncio
    async def test_llm_run_directive_none_treated_as_no_directive(self, mock_service):
        """None directive should behave same as no directive."""
        context = {
            "tenant_id": "test-tenant",
            "task_run_id": str(uuid.uuid4()),
            "session": MagicMock(),
            "directive": None,
        }

        cy_llm = CyLLMFunctions(mock_service, context)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_run(prompt="Test prompt")

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert "context" not in params

    @pytest.mark.asyncio
    async def test_directive_applies_to_all_llm_functions(
        self, mock_service, context_with_directive
    ):
        """Directive should apply to llm_summarize, llm_extract, llm_evaluate_results."""
        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            # llm_summarize calls llm_run internally
            await cy_llm.llm_summarize(text="Some analysis text", max_words=20)

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert params["context"] == "You are a senior security analyst. Be concise."

    @pytest.mark.asyncio
    async def test_llm_summarize_directive_param_overrides_context_directive(
        self, mock_service, context_with_directive
    ):
        """llm_summarize's own directive param should override the context directive."""
        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_summarize(
                text="Some text",
                directive="Custom summarization directive",
                max_words=20,
            )

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert params["context"] == "Custom summarization directive"

    @pytest.mark.asyncio
    async def test_response_content_still_returned_correctly(
        self, mock_service, context_with_directive
    ):
        """Directive injection should not affect the returned response."""
        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            result = await cy_llm.llm_run(prompt="Test")

        assert result == "LLM response"

    @pytest.mark.asyncio
    async def test_llm_extract_inherits_directive(
        self, mock_service, context_with_directive
    ):
        """llm_extract calls llm_run internally, so directive should apply."""
        mock_service.execute_action.return_value = _make_framework_result(
            '{"severity": "high", "threat_type": "malware"}'
        )

        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_extract(
                text="Malware detected on host",
                fields=["severity", "threat_type"],
            )

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert params["context"] == "You are a senior security analyst. Be concise."

    @pytest.mark.asyncio
    async def test_llm_evaluate_results_inherits_directive(
        self, mock_service, context_with_directive
    ):
        """llm_evaluate_results calls llm_run internally, so directive should apply."""
        mock_service.execute_action.return_value = _make_framework_result(
            '{"summary": "ok", "findings": [], "issues": [], "recommendations": []}'
        )

        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            await cy_llm.llm_evaluate_results(
                results={"findings": ["suspicious IP"]},
                criteria="security threat level",
            )

        call_kwargs = mock_service.execute_action.call_args.kwargs
        params = call_kwargs["params"]
        assert params["context"] == "You are a senior security analyst. Be concise."

    @pytest.mark.asyncio
    async def test_artifact_captures_prompt_string(
        self, mock_service, context_with_directive
    ):
        """Artifact should capture the user prompt as a string."""
        cy_llm = CyLLMFunctions(mock_service, context_with_directive)
        mock_artifact = AsyncMock()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", mock_artifact)

            await cy_llm.llm_run(prompt="Analyze this alert")

        call_kwargs = mock_artifact.call_args.kwargs
        assert call_kwargs["prompt"] == "Analyze this alert"
        assert isinstance(call_kwargs["prompt"], str)

    @pytest.mark.asyncio
    async def test_llm_summarize_restores_directive_after_override(
        self, mock_service, context_with_directive
    ):
        """After llm_summarize with its own directive, the context directive
        should be restored for subsequent llm_run calls."""
        cy_llm = CyLLMFunctions(mock_service, context_with_directive)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cy_llm, "_create_llm_artifact", AsyncMock())

            # First: summarize with custom directive
            await cy_llm.llm_summarize(
                text="Some text",
                directive="Custom directive",
                max_words=20,
            )

            # Second: regular llm_run should use the original context directive
            await cy_llm.llm_run(prompt="Follow-up analysis")

        # The second execute_action call should have the original directive
        second_call = mock_service.execute_action.call_args_list[-1]
        params = second_call.kwargs["params"]
        assert params["context"] == "You are a senior security analyst. Be concise."


@pytest.mark.unit
class TestDirectiveExecutionContextWiring:
    """Test that task directive flows from Task model into execution_context.

    These tests verify the wiring in task_execution.py that puts the
    directive into the execution_context dict consumed by CyLLMFunctions.
    """

    @pytest.mark.asyncio
    async def test_directive_included_in_execution_context_for_saved_task(self):
        """When a saved task has a directive, it should appear in execution_context."""
        from unittest.mock import patch

        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        # Mock task_run
        task_run = MagicMock()
        task_run.task_id = uuid.uuid4()
        task_run.id = uuid.uuid4()
        task_run.tenant_id = "test-tenant"
        task_run.workflow_run_id = None
        task_run.cy_script = 'return "hello"'
        task_run.execution_context = None

        # Mock the task object with directive
        mock_task = MagicMock()
        mock_task.directive = "You are a security analyst specialized in phishing."
        mock_task.script = 'return "hello"'
        mock_component = MagicMock()
        mock_component.cy_name = "test_task"
        mock_component.app = "default"
        mock_task.component = mock_component

        # Mock the session and its queries
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.refresh = AsyncMock()

        # Capture the execution_context passed to executor.execute()
        captured_context = {}

        async def capture_execute(script, input_data, execution_context=None):
            captured_context.update(execution_context or {})
            return {"status": "completed", "output": "hello"}

        with (
            patch.object(service.executor, "execute", side_effect=capture_execute),
            patch("analysi.services.task_run.TaskRunService") as mock_trs_cls,
            patch(
                "analysi.services.task_execution.TaskExecutionService._update_component_last_used_at_by_task",
                new=AsyncMock(),
            ),
        ):
            mock_trs = MagicMock()
            mock_trs.retrieve_input_data = AsyncMock(return_value={})
            mock_trs_cls.return_value = mock_trs

            await service._execute_task_with_session(task_run, mock_session)

        assert "directive" in captured_context
        assert (
            captured_context["directive"]
            == "You are a security analyst specialized in phishing."
        )

    @pytest.mark.asyncio
    async def test_directive_is_none_for_adhoc_task(self):
        """Ad-hoc tasks (no task_id) should have directive=None in context."""
        from unittest.mock import patch

        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        # Mock ad-hoc task_run (no task_id)
        task_run = MagicMock()
        task_run.task_id = None
        task_run.id = uuid.uuid4()
        task_run.tenant_id = "test-tenant"
        task_run.workflow_run_id = None
        task_run.cy_script = 'return "ad-hoc"'
        task_run.execution_context = None

        mock_session = AsyncMock()

        captured_context = {}

        async def capture_execute(script, input_data, execution_context=None):
            captured_context.update(execution_context or {})
            return {"status": "completed", "output": "ad-hoc"}

        with (
            patch.object(service.executor, "execute", side_effect=capture_execute),
            patch("analysi.services.task_run.TaskRunService") as mock_trs_cls,
        ):
            mock_trs = MagicMock()
            mock_trs.retrieve_input_data = AsyncMock(return_value={})
            mock_trs_cls.return_value = mock_trs

            await service._execute_task_with_session(task_run, mock_session)

        assert "directive" in captured_context
        assert captured_context["directive"] is None

    @pytest.mark.asyncio
    async def test_directive_none_when_task_has_no_directive(self):
        """Saved task with directive=None should pass None through."""
        from unittest.mock import patch

        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        task_run = MagicMock()
        task_run.task_id = uuid.uuid4()
        task_run.id = uuid.uuid4()
        task_run.tenant_id = "test-tenant"
        task_run.workflow_run_id = None
        task_run.cy_script = 'return "hello"'
        task_run.execution_context = None

        # Task exists but has no directive
        mock_task = MagicMock()
        mock_task.directive = None
        mock_task.script = 'return "hello"'
        mock_component = MagicMock()
        mock_component.cy_name = "test_task_no_directive"
        mock_component.app = "default"
        mock_task.component = mock_component

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.refresh = AsyncMock()

        captured_context = {}

        async def capture_execute(script, input_data, execution_context=None):
            captured_context.update(execution_context or {})
            return {"status": "completed", "output": "hello"}

        with (
            patch.object(service.executor, "execute", side_effect=capture_execute),
            patch("analysi.services.task_run.TaskRunService") as mock_trs_cls,
            patch(
                "analysi.services.task_execution.TaskExecutionService._update_component_last_used_at_by_task",
                new=AsyncMock(),
            ),
        ):
            mock_trs = MagicMock()
            mock_trs.retrieve_input_data = AsyncMock(return_value={})
            mock_trs_cls.return_value = mock_trs

            await service._execute_task_with_session(task_run, mock_session)

        assert "directive" in captured_context
        assert captured_context["directive"] is None

    @pytest.mark.asyncio
    async def test_workflow_context_cannot_override_task_directive(self):
        """A directive in task_run.execution_context (from workflow) must NOT
        override the task's own directive — task directive is authoritative."""
        from unittest.mock import patch

        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        task_run = MagicMock()
        task_run.task_id = uuid.uuid4()
        task_run.id = uuid.uuid4()
        task_run.tenant_id = "test-tenant"
        task_run.workflow_run_id = uuid.uuid4()
        task_run.cy_script = 'return "hello"'
        # Simulate workflow injecting a directive into execution_context
        task_run.execution_context = {"directive": "INJECTED BY WORKFLOW"}

        mock_task = MagicMock()
        mock_task.directive = "The real task directive"
        mock_task.script = 'return "hello"'
        mock_component = MagicMock()
        mock_component.cy_name = "test_task"
        mock_component.app = "default"
        mock_task.component = mock_component

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.refresh = AsyncMock()

        captured_context = {}

        async def capture_execute(script, input_data, execution_context=None):
            captured_context.update(execution_context or {})
            return {"status": "completed", "output": "hello"}

        with (
            patch.object(service.executor, "execute", side_effect=capture_execute),
            patch("analysi.services.task_run.TaskRunService") as mock_trs_cls,
            patch(
                "analysi.services.task_execution.TaskExecutionService._update_component_last_used_at_by_task",
                new=AsyncMock(),
            ),
        ):
            mock_trs = MagicMock()
            mock_trs.retrieve_input_data = AsyncMock(return_value={})
            mock_trs_cls.return_value = mock_trs

            await service._execute_task_with_session(task_run, mock_session)

        # Task directive must win over workflow-injected directive
        assert captured_context["directive"] == "The real task directive"


@pytest.mark.unit
class TestNestedTaskDirective:
    """Test that nested task_run() calls use the child task's directive,
    not the parent's."""

    @pytest.mark.asyncio
    async def test_child_task_gets_own_directive_not_parent(self):
        """When parent calls task_run('child'), the child's execution context
        should contain the child task's directive, not the parent's."""
        from unittest.mock import patch

        from analysi.services.cy_task_functions import CyTaskFunctions

        # Parent execution context with parent's directive
        parent_context = {
            "tenant_id": "test-tenant",
            "task_call_depth": 0,
            "app": "default",
            "directive": "Parent directive - I am the parent",
            "session": AsyncMock(),
        }

        task_functions = CyTaskFunctions(
            session=parent_context["session"],
            tenant_id="test-tenant",
            execution_context=parent_context,
        )

        # Mock the child task with its own directive
        mock_child_task = MagicMock()
        mock_child_task.directive = "Child directive - I am the child"
        mock_child_task.script = 'return "child result"'
        mock_child_task.component_id = uuid.uuid4()
        mock_component = MagicMock()
        mock_component.cy_name = "child_task"
        mock_component.app = "default"
        mock_component.status = "enabled"
        mock_child_task.component = mock_component

        # Capture the execution context passed to the child executor
        captured_child_context = {}

        async def capture_execute(cy_script, input_data, execution_context=None):
            captured_child_context.update(execution_context or {})
            return {"status": "completed", "output": "child result"}

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(side_effect=capture_execute)

        with (
            patch("analysi.repositories.task.TaskRepository") as mock_repo_cls,
            patch(
                "analysi.services.task_execution.DefaultTaskExecutor",
                return_value=mock_executor,
            ),
        ):
            mock_repo = AsyncMock()
            mock_repo.get_task_by_cy_name = AsyncMock(return_value=mock_child_task)
            mock_repo_cls.return_value = mock_repo

            await task_functions.task_run("child_task", {})

        # Child should have its OWN directive, not the parent's
        assert captured_child_context["directive"] == "Child directive - I am the child"

    @pytest.mark.asyncio
    async def test_child_task_with_no_directive_gets_none(self):
        """When child task has no directive, context should have None,
        not inherit the parent's directive."""
        from unittest.mock import patch

        from analysi.services.cy_task_functions import CyTaskFunctions

        parent_context = {
            "tenant_id": "test-tenant",
            "task_call_depth": 0,
            "app": "default",
            "directive": "Parent directive - should not leak",
            "session": AsyncMock(),
        }

        task_functions = CyTaskFunctions(
            session=parent_context["session"],
            tenant_id="test-tenant",
            execution_context=parent_context,
        )

        # Child task with NO directive
        mock_child_task = MagicMock()
        mock_child_task.directive = None
        mock_child_task.script = 'return "child"'
        mock_child_task.component_id = uuid.uuid4()
        mock_component = MagicMock()
        mock_component.cy_name = "child_no_directive"
        mock_component.app = "default"
        mock_component.status = "enabled"
        mock_child_task.component = mock_component

        captured_child_context = {}

        async def capture_execute(cy_script, input_data, execution_context=None):
            captured_child_context.update(execution_context or {})
            return {"status": "completed", "output": "child"}

        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(side_effect=capture_execute)

        with (
            patch("analysi.repositories.task.TaskRepository") as mock_repo_cls,
            patch(
                "analysi.services.task_execution.DefaultTaskExecutor",
                return_value=mock_executor,
            ),
        ):
            mock_repo = AsyncMock()
            mock_repo.get_task_by_cy_name = AsyncMock(return_value=mock_child_task)
            mock_repo_cls.return_value = mock_repo

            await task_functions.task_run("child_no_directive", {})

        # Child should NOT inherit parent's directive
        assert captured_child_context["directive"] is None
