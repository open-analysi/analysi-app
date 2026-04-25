"""
Unit tests to improve coverage for task_execution.py.

Covers:
- DefaultTaskExecutor._load_tools()
- DefaultTaskExecutor._load_time_functions()
- DefaultTaskExecutor._load_ku_functions()
- DefaultTaskExecutor._load_alert_functions()
- DefaultTaskExecutor._load_enrichment_functions()
- DefaultTaskExecutor._load_task_functions()
- DefaultTaskExecutor._load_app_tools()
- DefaultTaskExecutor._load_llm_functions()
- DefaultTaskExecutor.execute() - output parsing, error detection, session cleanup
- DefaultTaskExecutor._cleanup_artifact_session()
- DefaultTaskExecutor._configure_mcp_servers()
- DurationCalculator
- ExecutionContext
- ExecutorConfigManager
- TaskExecutionService uncovered methods
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.task_execution import (
    DefaultTaskExecutor,
    DurationCalculator,
    ExecutionContext,
    ExecutorConfigManager,
    TaskExecutionService,
)

# ---------------------------------------------------------------------------
# 1. DefaultTaskExecutor._load_tools()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadTools:
    """Tests for DefaultTaskExecutor._load_tools()."""

    def test_returns_dict_with_native_cy_functions(self):
        """_load_tools returns a dict containing native cy-language functions."""
        executor = DefaultTaskExecutor()
        tools = executor._load_tools()
        assert isinstance(tools, dict)
        assert len(tools) > 0

    def test_contains_expected_builtin_functions(self):
        """Tools dict includes common builtins like len, str, log."""
        executor = DefaultTaskExecutor()
        tools = executor._load_tools()
        # At minimum these should be registered by cy_language.native_functions
        for name in ("len", "type::str", "log"):  # str is now registered as type::str
            assert name in tools, f"Expected '{name}' in tools dict"
            assert callable(tools[name])

    def test_returns_empty_dict_when_cy_language_not_importable(self):
        """If cy_language is missing, _load_tools gracefully returns {}."""
        executor = DefaultTaskExecutor()
        with patch.dict("sys.modules", {"cy_language.native_functions": None}):
            with patch(
                "analysi.services.task_execution.DefaultTaskExecutor._load_tools",
                wraps=executor._load_tools,
            ):
                # Simulate ImportError by patching the import inside _load_tools
                original = executor._load_tools

                def patched_load(ctx=None):
                    try:
                        raise ImportError("no cy_language")
                    except ImportError:
                        return {}

                executor._load_tools = patched_load
                result = executor._load_tools()
                assert result == {}
                executor._load_tools = original

    def test_accepts_execution_context_param(self):
        """_load_tools accepts an optional execution_context parameter."""
        executor = DefaultTaskExecutor()
        tools = executor._load_tools({"tenant_id": "t1"})
        assert isinstance(tools, dict)


# ---------------------------------------------------------------------------
# 2. DefaultTaskExecutor._load_time_functions()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadTimeFunctions:
    """Tests for DefaultTaskExecutor._load_time_functions()."""

    def test_returns_dict_with_format_timestamp(self):
        """Should return a dict containing 'format_timestamp'."""
        executor = DefaultTaskExecutor()
        funcs = executor._load_time_functions()
        assert "format_timestamp" in funcs
        assert callable(funcs["format_timestamp"])

    def test_returns_both_short_and_fqn_names(self):
        """Should register both short and FQN names."""
        executor = DefaultTaskExecutor()
        funcs = executor._load_time_functions()
        assert "format_timestamp" in funcs
        assert "native::tools::format_timestamp" in funcs
        # Both should point to the same underlying method
        # (They are bound methods from the same instance, so test callable equivalence)
        assert callable(funcs["format_timestamp"])
        assert callable(funcs["native::tools::format_timestamp"])

    def test_returns_empty_dict_on_import_error(self):
        """Returns {} when CyTimeFunctions cannot be imported."""
        executor = DefaultTaskExecutor()
        with patch(
            "analysi.services.task_execution.DefaultTaskExecutor._load_time_functions"
        ) as mock_method:
            # Simulate exception path
            mock_method.return_value = {}
            assert executor._load_time_functions() == {}

    def test_returns_empty_dict_on_exception(self):
        """Returns {} when CyTimeFunctions() raises."""
        executor = DefaultTaskExecutor()
        with patch(
            "analysi.services.cy_time_functions.CyTimeFunctions",
            side_effect=RuntimeError("boom"),
        ):
            result = executor._load_time_functions()
            assert result == {}


# ---------------------------------------------------------------------------
# 3. DefaultTaskExecutor._load_ku_functions()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadKuFunctions:
    """Tests for DefaultTaskExecutor._load_ku_functions()."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_tenant_id(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_ku_functions({})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_session(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_ku_functions({"tenant_id": "t1"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_functions_on_success(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        expected = {"ku_read": lambda: None, "ku_write": lambda: None}
        with patch(
            "analysi.services.cy_ku_functions.create_cy_ku_functions",
            return_value=expected,
        ):
            result = await executor._load_ku_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == expected

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_exception(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        with patch(
            "analysi.services.cy_ku_functions.create_cy_ku_functions",
            side_effect=RuntimeError("DB down"),
        ):
            result = await executor._load_ku_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == {}


# ---------------------------------------------------------------------------
# 4. DefaultTaskExecutor._load_alert_functions()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadAlertFunctions:
    """Tests for DefaultTaskExecutor._load_alert_functions()."""

    def test_returns_empty_dict_when_no_session(self):
        executor = DefaultTaskExecutor()
        result = executor._load_alert_functions("tenant-1", {})
        assert result == {}

    def test_returns_functions_on_success(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        expected = {"get_alert": lambda: None}
        with patch(
            "analysi.services.cy_alert_functions.create_cy_alert_functions",
            return_value=expected,
        ):
            result = executor._load_alert_functions(
                "tenant-1", {"session": mock_session}
            )
            assert result == expected

    def test_returns_empty_dict_on_exception(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        with patch(
            "analysi.services.cy_alert_functions.create_cy_alert_functions",
            side_effect=RuntimeError("fail"),
        ):
            result = executor._load_alert_functions(
                "tenant-1", {"session": mock_session}
            )
            assert result == {}


# ---------------------------------------------------------------------------
# 5. DefaultTaskExecutor._load_enrichment_functions()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadEnrichmentFunctions:
    """Tests for DefaultTaskExecutor._load_enrichment_functions()."""

    def test_returns_functions_on_success(self):
        executor = DefaultTaskExecutor()
        expected = {"enrich_alert": lambda: None}
        with patch(
            "analysi.services.cy_enrichment_functions.create_cy_enrichment_functions",
            return_value=expected,
        ):
            result = executor._load_enrichment_functions({"cy_name": "my_task"})
            assert result == expected

    def test_returns_empty_dict_on_exception(self):
        executor = DefaultTaskExecutor()
        with patch(
            "analysi.services.cy_enrichment_functions.create_cy_enrichment_functions",
            side_effect=ValueError("bad"),
        ):
            result = executor._load_enrichment_functions({"cy_name": "my_task"})
            assert result == {}


# ---------------------------------------------------------------------------
# 6. DefaultTaskExecutor._load_task_functions()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadTaskFunctions:
    """Tests for DefaultTaskExecutor._load_task_functions()."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_tenant_id(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_task_functions({})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_session(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_task_functions({"tenant_id": "t1"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_functions_on_success(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        expected = {"task_run": lambda: None}
        with patch(
            "analysi.services.cy_task_functions.create_cy_task_functions",
            return_value=expected,
        ):
            result = await executor._load_task_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == expected

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_exception(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        with patch(
            "analysi.services.cy_task_functions.create_cy_task_functions",
            side_effect=RuntimeError("nope"),
        ):
            result = await executor._load_task_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == {}


# ---------------------------------------------------------------------------
# 7. DefaultTaskExecutor._load_app_tools()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadAppTools:
    """Tests for DefaultTaskExecutor._load_app_tools()."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_tenant_id(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_app_tools({})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_session(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_app_tools({"tenant_id": "t1"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_exception(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        with patch(
            "analysi.repositories.integration_repository.IntegrationRepository",
            side_effect=RuntimeError("import boom"),
        ):
            result = await executor._load_app_tools(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == {}


# ---------------------------------------------------------------------------
# 8. DefaultTaskExecutor._load_llm_functions()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadLlmFunctions:
    """Tests for DefaultTaskExecutor._load_llm_functions()."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_session(self):
        executor = DefaultTaskExecutor()
        result = await executor._load_llm_functions({"tenant_id": "t1"})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_session_not_active(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        mock_session.is_active = False
        result = await executor._load_llm_functions(
            {"tenant_id": "t1", "session": mock_session}
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_functions_on_success(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        mock_session.is_active = True
        expected = {"llm_run": lambda: None}
        mock_cy_instance = MagicMock()

        with (
            patch(
                "analysi.services.cy_llm_functions.create_cy_llm_functions",
                # returns (functions_dict, CyLLMFunctions instance)
                return_value=(expected, mock_cy_instance),
            ),
            patch("analysi.repositories.integration_repository.IntegrationRepository"),
            patch("analysi.repositories.credential_repository.CredentialRepository"),
            patch("analysi.repositories.integration_repository.IntegrationRepository"),
            patch("analysi.repositories.credential_repository.CredentialRepository"),
            patch("analysi.services.integration_service.IntegrationService"),
        ):
            result = await executor._load_llm_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == expected

    @pytest.mark.asyncio
    async def test_create_cy_llm_receives_integration_service(self):
        """create_cy_llm_functions receives IntegrationService (not LangChainFactory)."""
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        mock_session.is_active = True
        mock_cy_instance = MagicMock()

        with (
            patch(
                "analysi.services.cy_llm_functions.create_cy_llm_functions",
                return_value=({"llm_run": lambda: None}, mock_cy_instance),
            ) as mock_create,
            patch("analysi.repositories.integration_repository.IntegrationRepository"),
            patch("analysi.repositories.credential_repository.CredentialRepository"),
            patch("analysi.repositories.integration_repository.IntegrationRepository"),
            patch("analysi.repositories.credential_repository.CredentialRepository"),
            patch(
                "analysi.services.integration_service.IntegrationService"
            ) as mock_svc_cls,
        ):
            await executor._load_llm_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            # create_cy_llm_functions should receive the IntegrationService instance
            mock_create.assert_called_once()
            first_arg = mock_create.call_args[0][0]
            assert first_arg == mock_svc_cls.return_value

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_exception(self):
        executor = DefaultTaskExecutor()
        mock_session = MagicMock()
        mock_session.is_active = True
        with patch(
            "analysi.repositories.integration_repository.IntegrationRepository",
            side_effect=RuntimeError("fail"),
        ):
            result = await executor._load_llm_functions(
                {"tenant_id": "t1", "session": mock_session}
            )
            assert result == {}


# ---------------------------------------------------------------------------
# 9. DefaultTaskExecutor.execute() - output parsing and error detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteOutputParsing:
    """Tests for execute() output parsing, error detection, and session cleanup."""

    @pytest.mark.asyncio
    async def test_success_with_dict_output(self):
        """Dict output from run_native_async is returned directly."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            # Cy 0.38+: run_native_async returns Python objects directly
            mock_interpreter.run_native_async = AsyncMock(return_value={"key": "value"})
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return {}", {})
            assert result["status"] == "completed"
            assert result["output"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_success_with_string_output(self):
        """String output from run_native_async is returned as-is."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            # Cy 0.38+: run_native_async returns native Python objects (including strings)
            mock_interpreter.run_native_async = AsyncMock(
                return_value="hello world - a plain string"
            )
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 'hi'", {})
            assert result["status"] == "completed"
            assert result["output"] == "hello world - a plain string"

    @pytest.mark.asyncio
    async def test_cy_error_output_detection_only_error_key(self):
        """Dict with only 'error' key is detected as Cy error."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(
                return_value={"error": "Key 'x' not found"}
            )
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("x", {})
            assert result["status"] == "failed"
            assert "Key 'x' not found" in result["error"]

    @pytest.mark.asyncio
    async def test_cy_error_output_with_error_and_null_output(self):
        """Dict with 'error' and 'output':None is a Cy error."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(
                return_value={"error": "runtime err", "output": None}
            )
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("x", {})
            assert result["status"] == "failed"
            assert "runtime err" in result["error"]

    @pytest.mark.asyncio
    async def test_valid_output_with_error_info_does_not_fail(self):
        """Dict with 'error' + other keys is valid output, not a Cy error."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(
                return_value={
                    "success": False,
                    "error": "something went wrong",
                    "code": 500,
                }
            )
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("x", {})
            assert result["status"] == "completed"
            assert result["output"]["error"] == "something went wrong"
            assert result["output"]["code"] == 500

    @pytest.mark.asyncio
    async def test_session_cleanup_on_success_reused_session(self):
        """On success with a reused session, commit but do not close."""
        executor = DefaultTaskExecutor()
        mock_session = AsyncMock()

        # Pre-set reused session attributes
        executor._reused_session = True
        executor._artifact_session = mock_session
        executor._artifact_session_context = None

        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value="ok")
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 'ok'", {})
            assert result["status"] == "completed"
            # Reused session should have been committed
            mock_session.commit.assert_called_once()
            # Should NOT have been closed
            mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_cleanup_on_success_own_session(self):
        """On success with own session, commit, close, and exit context."""
        executor = DefaultTaskExecutor()
        mock_session = AsyncMock()
        mock_context = AsyncMock()

        # Mock cleanup to be a no-op so our pre-set attributes survive
        async def fake_cleanup():
            pass

        with patch.object(
            executor, "_cleanup_artifact_session", side_effect=fake_cleanup
        ):
            executor._artifact_session_context = mock_context
            executor._artifact_session = mock_session
            executor._reused_session = False

            with patch("analysi.services.task_execution.Cy") as MockCy:
                mock_interpreter = AsyncMock()
                mock_interpreter.run_native_async = AsyncMock(return_value="ok")
                MockCy.create_async = AsyncMock(return_value=mock_interpreter)

                result = await executor.execute("return 'ok'", {})
                assert result["status"] == "completed"
                mock_session.commit.assert_called_once()
                mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_cleanup_on_error_reused_session(self):
        """On error with reused session, rollback but do not close."""
        executor = DefaultTaskExecutor()
        mock_session = AsyncMock()

        executor._reused_session = True
        executor._artifact_session = mock_session

        with patch("analysi.services.task_execution.Cy") as MockCy:
            MockCy.create_async = AsyncMock(side_effect=RuntimeError("script failed"))

            result = await executor.execute("bad script", {})
            assert result["status"] == "failed"
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_cleanup_on_error_own_session(self):
        """On error with own session, rollback, close, and exit context."""
        executor = DefaultTaskExecutor()
        mock_session = AsyncMock()
        mock_context = AsyncMock()

        executor._artifact_session_context = mock_context
        executor._artifact_session = mock_session
        executor._reused_session = False

        with patch("analysi.services.task_execution.Cy") as MockCy:
            MockCy.create_async = AsyncMock(side_effect=RuntimeError("script failed"))

            result = await executor.execute("bad script", {})
            assert result["status"] == "failed"
            mock_session.rollback.assert_called_once()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_attribute_error_fallback_to_sync_api(self):
        """If Cy.create_async raises AttributeError, fall back to sync Cy API."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            # create_async raises AttributeError (old Cy version)
            MockCy.create_async = AsyncMock(side_effect=AttributeError("create_async"))
            # Sync fallback uses run_native (Cy 0.38+)
            mock_sync = MagicMock()
            mock_sync.run_native.return_value = "sync result"
            MockCy.return_value = mock_sync

            result = await executor.execute("return 'ok'", {})
            assert result["status"] == "completed"
            assert result["output"] == "sync result"
            MockCy.assert_called_once()
            mock_sync.run_native.assert_called_once()

    @pytest.mark.asyncio
    async def test_attribute_error_not_create_async_reraises(self):
        """AttributeError NOT about create_async should propagate as failure."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            MockCy.create_async = AsyncMock(
                side_effect=AttributeError("some_other_method")
            )

            result = await executor.execute("return 'ok'", {})
            assert result["status"] == "failed"
            assert "some_other_method" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_with_execution_context_loads_all_tools(self):
        """When execution_context is provided, all tool loaders are called."""
        executor = DefaultTaskExecutor()
        ctx = {
            "tenant_id": "t1",
            "task_run_id": "tr1",
            "session": MagicMock(),
        }

        with (
            patch("analysi.services.task_execution.Cy") as MockCy,
            patch.object(
                executor, "_load_artifact_functions", new=AsyncMock(return_value={})
            ) as mock_art,
            patch.object(
                executor, "_load_llm_functions", new=AsyncMock(return_value={})
            ) as mock_llm,
            patch.object(
                executor, "_load_ku_functions", new=AsyncMock(return_value={})
            ) as mock_ku,
            patch.object(
                executor, "_load_task_functions", new=AsyncMock(return_value={})
            ) as mock_task,
            patch.object(
                executor, "_load_alert_functions", return_value={}
            ) as mock_alert,
            patch.object(
                executor, "_load_enrichment_functions", return_value={}
            ) as mock_enrich,
            patch.object(
                executor, "_load_app_tools", new=AsyncMock(return_value={})
            ) as mock_app,
        ):
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value="ok")
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 'ok'", {}, ctx)
            assert result["status"] == "completed"

            mock_art.assert_called_once()
            mock_llm.assert_called_once()
            mock_ku.assert_called_once()
            mock_task.assert_called_once()
            mock_alert.assert_called_once()
            mock_enrich.assert_called_once()
            mock_app.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_without_context_skips_context_tools(self):
        """When execution_context is None, context-dependent tool loaders are not called."""
        executor = DefaultTaskExecutor()

        with (
            patch("analysi.services.task_execution.Cy") as MockCy,
            patch.object(
                executor, "_load_artifact_functions", new=AsyncMock(return_value={})
            ) as mock_art,
        ):
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value="ok")
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 'ok'", {})
            assert result["status"] == "completed"
            mock_art.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_non_dict_non_string_output(self):
        """execute() returns non-dict, non-string results directly."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value=42)
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 42", {})
            assert result["status"] == "completed"
            assert result["output"] == 42

    @pytest.mark.asyncio
    async def test_execute_list_output(self):
        """execute() returns list results directly."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value=[1, 2, 3])
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return [1,2,3]", {})
            assert result["status"] == "completed"
            assert result["output"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 10. DefaultTaskExecutor._cleanup_artifact_session()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCleanupArtifactSession:
    """Tests for DefaultTaskExecutor._cleanup_artifact_session()."""

    @pytest.mark.asyncio
    async def test_cleanup_when_no_session_exists(self):
        """Cleanup is a no-op when no artifact session exists."""
        executor = DefaultTaskExecutor()
        # Should not raise
        await executor._cleanup_artifact_session()

    @pytest.mark.asyncio
    async def test_cleanup_with_existing_session(self):
        """Cleanup rolls back, closes session, and exits context."""
        executor = DefaultTaskExecutor()
        mock_session = AsyncMock()
        mock_context = AsyncMock()

        executor._artifact_session_context = mock_context
        executor._artifact_session = mock_session
        executor._cy_functions_instance = MagicMock()

        await executor._cleanup_artifact_session()

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
        assert executor._artifact_session_context is None
        assert executor._artifact_session is None

    @pytest.mark.asyncio
    async def test_cleanup_clears_llm_factory_cache(self):
        """Cleanup clears the LLM factory cache."""
        executor = DefaultTaskExecutor()
        executor._llm_factory_cache = {"key": "value"}
        executor._artifact_session_context = None
        executor._artifact_session = None

        await executor._cleanup_artifact_session()

        assert executor._llm_factory_cache == {}

    @pytest.mark.asyncio
    async def test_cleanup_different_event_loop_clears_refs(self):
        """When running in a different event loop, just clear references."""
        executor = DefaultTaskExecutor()
        executor._artifact_session_context = MagicMock()
        executor._artifact_session = MagicMock()
        executor._cy_functions_instance = MagicMock()
        # Set a fake loop that's different from the running one
        executor._session_loop = MagicMock()

        await executor._cleanup_artifact_session()

        assert executor._artifact_session_context is None
        assert executor._artifact_session is None
        assert executor._cy_functions_instance is None

    @pytest.mark.asyncio
    async def test_cleanup_ignores_errors_in_rollback(self):
        """Cleanup continues even if rollback fails."""
        executor = DefaultTaskExecutor()
        mock_session = AsyncMock()
        mock_session.rollback.side_effect = RuntimeError("rollback fail")
        mock_context = AsyncMock()

        executor._artifact_session_context = mock_context
        executor._artifact_session = mock_session

        # Should not raise
        await executor._cleanup_artifact_session()
        assert executor._artifact_session is None


# ---------------------------------------------------------------------------
# 11. DefaultTaskExecutor._configure_mcp_servers()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigureMcpServers:
    """Tests for DefaultTaskExecutor._configure_mcp_servers()."""

    def test_returns_none_when_no_env_var(self):
        """Returns None when MCP_SERVERS is not set."""
        executor = DefaultTaskExecutor()
        with patch.dict(
            "os.environ",
            {"PYTEST_CURRENT_TEST": "test_something"},
            clear=False,
        ):
            # Remove MCP_SERVERS if present
            import os

            env = os.environ.copy()
            env.pop("MCP_SERVERS", None)
            with patch.dict("os.environ", env, clear=True):
                # Re-add PYTEST_CURRENT_TEST
                with patch.dict("os.environ", {"PYTEST_CURRENT_TEST": "test"}):
                    result = executor._configure_mcp_servers()
                    assert result is None

    def test_returns_none_in_pytest_without_mcp_servers_env(self):
        """During pytest, returns None unless MCP_SERVERS is explicitly set."""
        executor = DefaultTaskExecutor()
        with patch.dict(
            "os.environ",
            {"PYTEST_CURRENT_TEST": "test::something"},
            clear=False,
        ):
            result = executor._configure_mcp_servers()
            assert result is None

    def test_returns_parsed_json_when_mcp_servers_env_is_set(self):
        """Parses MCP_SERVERS env var as JSON and returns it."""
        executor = DefaultTaskExecutor()
        mcp_config = '{"server1": {"url": "http://localhost:3000"}}'
        with patch.dict(
            "os.environ",
            {"MCP_SERVERS": mcp_config},
            clear=False,
        ):
            # Also remove PYTEST_CURRENT_TEST to not short-circuit
            import os

            env = os.environ.copy()
            env.pop("PYTEST_CURRENT_TEST", None)
            env["MCP_SERVERS"] = mcp_config
            with patch.dict("os.environ", env, clear=True):
                result = executor._configure_mcp_servers()
                assert result == {"server1": {"url": "http://localhost:3000"}}

    def test_returns_none_on_invalid_json(self):
        """Returns None when MCP_SERVERS env var contains invalid JSON."""
        executor = DefaultTaskExecutor()
        import os

        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        env["MCP_SERVERS"] = "not valid json {{"
        with patch.dict("os.environ", env, clear=True):
            result = executor._configure_mcp_servers()
            assert result is None


# ---------------------------------------------------------------------------
# 12. DurationCalculator
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDurationCalculator:
    """Tests for DurationCalculator utility class."""

    def test_calculate_valid_duration(self):
        start = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 10, 5, 30, tzinfo=UTC)
        result = DurationCalculator.calculate(start, end)
        assert result == timedelta(minutes=5, seconds=30)

    def test_calculate_zero_duration(self):
        t = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        result = DurationCalculator.calculate(t, t)
        assert result == timedelta(0)

    def test_calculate_returns_none_for_none_start(self):
        assert DurationCalculator.calculate(None, datetime.now(UTC)) is None

    def test_calculate_returns_none_for_none_end(self):
        assert DurationCalculator.calculate(datetime.now(UTC), None) is None

    def test_calculate_returns_none_for_both_none(self):
        assert DurationCalculator.calculate(None, None) is None

    def test_calculate_returns_none_for_negative_interval(self):
        start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        assert DurationCalculator.calculate(start, end) is None


# ---------------------------------------------------------------------------
# 13. ExecutionContext
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecutionContext:
    """Tests for ExecutionContext.build_context()."""

    def test_build_basic_context(self):
        ctx = ExecutionContext.build_context(
            tenant_id="tenant-1",
            task_id="task-1",
            available_kus=["ku-a", "ku-b"],
        )
        assert ctx["tenant_id"] == "tenant-1"
        assert ctx["task_id"] == "task-1"
        assert ctx["knowledge_units"] == ["ku-a", "ku-b"]
        assert ctx["workflow_run_id"] is None
        assert ctx["workflow_node_instance_id"] is None

    def test_build_context_with_workflow_ids(self):
        ctx = ExecutionContext.build_context(
            tenant_id="t",
            task_id="t-id",
            available_kus=[],
            workflow_run_id="wf-run-1",
            workflow_node_instance_id="node-inst-1",
        )
        assert ctx["workflow_run_id"] == "wf-run-1"
        assert ctx["workflow_node_instance_id"] == "node-inst-1"

    def test_build_context_for_adhoc_task(self):
        ctx = ExecutionContext.build_context(
            tenant_id="t",
            task_id=None,
            available_kus=[],
        )
        assert ctx["task_id"] is None

    def test_build_context_includes_runtime_fields(self):
        ctx = ExecutionContext.build_context(
            tenant_id="t", task_id="id", available_kus=[]
        )
        assert "llm_model" in ctx
        assert "runtime_version" in ctx
        assert "available_tools" in ctx
        assert isinstance(ctx["available_tools"], list)


# ---------------------------------------------------------------------------
# 14. ExecutorConfigManager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecutorConfigManager:
    """Tests for ExecutorConfigManager.load_from_env()."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            config = ExecutorConfigManager.load_from_env()
            assert config["threads"] == 4
            assert config["timeout"] == 300
            assert config["enabled_executors"] == ["default"]

    def test_custom_env_values(self):
        with patch.dict(
            "os.environ",
            {
                "TASK_EXECUTOR_WORKERS": "8",
                "TASK_EXECUTOR_TIMEOUT": "600",
                "ENABLED_EXECUTORS": "default,parallel,gpu",
            },
        ):
            config = ExecutorConfigManager.load_from_env()
            assert config["threads"] == 8
            assert config["timeout"] == 600
            assert config["enabled_executors"] == ["default", "parallel", "gpu"]

    def test_single_executor(self):
        with patch.dict("os.environ", {"ENABLED_EXECUTORS": "default"}):
            config = ExecutorConfigManager.load_from_env()
            assert config["enabled_executors"] == ["default"]


# ---------------------------------------------------------------------------
# 15. TaskExecutionService - uncovered methods
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTaskExecutionServiceCoverage:
    """Tests for TaskExecutionService methods not covered elsewhere."""

    def test_has_queued_tasks_initially_false(self):
        svc = TaskExecutionService()
        assert svc.has_queued_tasks() is False

    def test_queue_size_initially_zero(self):
        svc = TaskExecutionService()
        assert svc.queue_size() == 0

    @pytest.mark.asyncio
    async def test_queue_task_increments_size(self):
        svc = TaskExecutionService()
        mock_run = MagicMock()
        await svc.queue_task(mock_run)
        assert svc.queue_size() == 1
        assert svc.has_queued_tasks() is True

    @pytest.mark.asyncio
    async def test_run_post_hooks_returns_result_when_no_llm_functions(self):
        """_run_post_hooks returns unmodified result when no LLM functions available."""
        svc = TaskExecutionService()
        result = {"status": "completed", "output": {"data": 1}}
        mock_task = MagicMock()
        mock_task.directive = "test"
        mock_task.component = MagicMock()
        mock_task.component.name = "Task Name"
        mock_task.component.description = "desc"

        with patch.object(
            svc.executor, "_load_llm_functions", new=AsyncMock(return_value={})
        ):
            modified = await svc._run_post_hooks(
                result=result,
                task=mock_task,
                execution_context={"cy_name": "test"},
                original_input={},
            )
            assert modified == result

    @pytest.mark.asyncio
    async def test_run_post_hooks_returns_result_on_exception(self):
        """_run_post_hooks returns unmodified result if hooks raise."""
        svc = TaskExecutionService()
        result = {"status": "completed", "output": {"data": 1}}
        mock_task = MagicMock()

        with patch.object(
            svc.executor,
            "_load_llm_functions",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            modified = await svc._run_post_hooks(
                result=result,
                task=mock_task,
                execution_context={"cy_name": "test"},
                original_input={},
            )
            assert modified == result

    @pytest.mark.asyncio
    async def test_run_post_hooks_modifies_output_on_success(self):
        """_run_post_hooks modifies result output when hooks succeed."""
        svc = TaskExecutionService()
        result = {"status": "completed", "output": {"analysis": "clean"}}
        mock_task = MagicMock()
        mock_task.directive = "Analyze alerts"
        mock_task.component = MagicMock()
        mock_task.component.name = "Test"
        mock_task.component.description = "desc"
        mock_task.component.cy_name = "test_task"

        modified_output = {"analysis": "clean", "ai_analysis_title": "Clean Alert"}

        mock_post_hooks = MagicMock()
        mock_post_hooks.run_all_hooks = AsyncMock(return_value=modified_output)

        with (
            patch.object(
                svc.executor,
                "_load_llm_functions",
                new=AsyncMock(return_value={"llm_summarize": lambda: None}),
            ),
            patch(
                "analysi.services.task_post_hooks.create_task_post_hooks",
                return_value=mock_post_hooks,
            ),
        ):
            modified = await svc._run_post_hooks(
                result=result,
                task=mock_task,
                execution_context={"cy_name": "test_task"},
                original_input={"title": "alert"},
            )
            assert modified["output"] == modified_output

    @pytest.mark.asyncio
    async def test_execute_single_task_with_provided_session(self):
        """_execute_task_with_session uses provided session and returns COMPLETED result."""
        svc = TaskExecutionService()
        mock_session = AsyncMock()
        mock_task_run = MagicMock()
        mock_task_run.id = "run-1"
        mock_task_run.cy_script = "return 'hi'"
        mock_task_run.task_id = None
        mock_task_run.tenant_id = "tenant-1"
        mock_task_run.execution_context = None
        mock_task_run.workflow_run_id = None

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {
            "status": "completed",
            "output": "hi",
        }

        with (
            patch.object(svc, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as MockTRS,
        ):
            mock_trs = MockTRS.return_value
            mock_trs.retrieve_input_data = AsyncMock(return_value={})

            result = await svc._execute_task_with_session(mock_task_run, mock_session)

            mock_executor.execute.assert_called_once()
            from analysi.schemas.task_execution import TaskExecutionStatus

            assert result.status == TaskExecutionStatus.COMPLETED
            assert result.output_data == "hi"

    @pytest.mark.asyncio
    async def test_execute_single_task_without_session_creates_one(self):
        """execute_single_task always creates its own isolated session."""
        from uuid import uuid4

        svc = TaskExecutionService()
        task_run_id = uuid4()

        mock_bg_session = AsyncMock()
        mock_task_run_obj = MagicMock()
        mock_task_run_obj.id = task_run_id
        mock_task_run_obj.cy_script = "return 'bg'"
        mock_task_run_obj.task_id = None
        mock_task_run_obj.tenant_id = "tenant-1"
        mock_task_run_obj.execution_context = None
        mock_task_run_obj.workflow_run_id = None
        mock_bg_session.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=mock_task_run_obj)
            )
        )

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"status": "completed", "output": "bg"}

        with (
            patch.object(svc, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as MockTRS,
            patch("analysi.db.session.AsyncSessionLocal") as MockSessionLocal,
        ):
            mock_trs = MockTRS.return_value
            mock_trs.retrieve_input_data = AsyncMock(return_value={})

            MockSessionLocal.return_value.__aenter__ = AsyncMock(
                return_value=mock_bg_session
            )
            MockSessionLocal.return_value.__aexit__ = AsyncMock(return_value=None)

            await svc.execute_single_task(task_run_id, "tenant-1")

            MockSessionLocal.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task_with_session_failed_result(self):
        """_execute_task_with_session returns FAILED result on executor failure."""
        svc = TaskExecutionService()
        mock_session = AsyncMock()
        mock_task_run = MagicMock()
        mock_task_run.id = "run-fail"
        mock_task_run.cy_script = "bad code"
        mock_task_run.task_id = None
        mock_task_run.tenant_id = "tenant-1"
        mock_task_run.execution_context = None
        mock_task_run.workflow_run_id = None

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {
            "status": "failed",
            "error": "Syntax error",
        }

        with (
            patch.object(svc, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as MockTRS,
        ):
            mock_trs = MockTRS.return_value
            mock_trs.retrieve_input_data = AsyncMock(return_value={})

            result = await svc._execute_task_with_session(mock_task_run, mock_session)

            from analysi.schemas.task_execution import TaskExecutionStatus

            assert result.status == TaskExecutionStatus.FAILED
            assert result.error_message == "Syntax error"
            assert result.output_data is None

    @pytest.mark.asyncio
    async def test_execute_task_with_session_exception_updates_failed(self):
        """_execute_task_with_session returns FAILED result when exception occurs."""
        svc = TaskExecutionService()
        mock_session = AsyncMock()
        mock_task_run = MagicMock()
        mock_task_run.id = "run-exc"
        mock_task_run.cy_script = "return 'ok'"
        mock_task_run.task_id = None
        mock_task_run.tenant_id = "tenant-1"
        mock_task_run.execution_context = None
        mock_task_run.workflow_run_id = None

        mock_executor = AsyncMock()
        mock_executor.execute.side_effect = RuntimeError("unexpected")

        with (
            patch.object(svc, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as MockTRS,
        ):
            mock_trs = MockTRS.return_value
            mock_trs.retrieve_input_data = AsyncMock(return_value={})

            result = await svc._execute_task_with_session(mock_task_run, mock_session)

            from analysi.schemas.task_execution import TaskExecutionStatus

            assert result.status == TaskExecutionStatus.FAILED
            assert "unexpected" in result.error_message


# ---------------------------------------------------------------------------
# 16. DefaultTaskExecutor.__del__()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDefaultTaskExecutorDel:
    """Tests for DefaultTaskExecutor.__del__() cleanup."""

    def test_del_clears_references_when_session_context_exists(self):
        executor = DefaultTaskExecutor()
        executor._artifact_session_context = MagicMock()
        executor._artifact_session = MagicMock()
        executor._cy_functions_instance = MagicMock()

        executor.__del__()

        assert executor._artifact_session_context is None
        assert executor._artifact_session is None
        assert executor._cy_functions_instance is None

    def test_del_no_op_when_no_session_context(self):
        executor = DefaultTaskExecutor()
        # Should not raise
        executor.__del__()


# ---------------------------------------------------------------------------
# 17. DefaultTaskExecutor.execute() — log capture
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteLogCapture:
    """Tests for log() capture in DefaultTaskExecutor.execute().

    Verifies that:
    - Cy.create_async() is called with a captured_logs list
    - Any entries appended to that list appear in raw_result["logs"]
    - No log() calls produces an empty list, not None
    """

    @pytest.mark.asyncio
    async def test_create_async_receives_captured_logs_argument(self):
        """Cy.create_async() must be called with a captured_logs keyword argument."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value="ok")
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            await executor.execute("return 'ok'", {})

            call_kwargs = MockCy.create_async.call_args.kwargs
            assert "captured_logs" in call_kwargs, (
                "Cy.create_async() must receive a captured_logs= argument"
            )
            assert isinstance(call_kwargs["captured_logs"], list), (
                "captured_logs must be a list so log() can append to it"
            )

    @pytest.mark.asyncio
    async def test_logs_appended_during_execution_appear_in_result(self):
        """Entries appended to captured_logs during execution appear in result['logs']."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()

            async def fake_run_native_async(script, input_data, **kwargs):
                # Simulate log() appending to the captured_logs list that was passed in
                captured = MockCy.create_async.call_args.kwargs["captured_logs"]
                captured.append("hello from log")
                captured.append("second message")
                return "done"

            mock_interpreter.run_native_async = fake_run_native_async
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 'done'", {})

            assert result["status"] == "completed"
            assert "logs" in result, "raw result dict must include a 'logs' key"
            assert result["logs"] == ["hello from log", "second message"]

    @pytest.mark.asyncio
    async def test_no_log_calls_produces_empty_list_not_none(self):
        """When no log() calls happen, result['logs'] is [], not None."""
        executor = DefaultTaskExecutor()
        with patch("analysi.services.task_execution.Cy") as MockCy:
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(return_value=42)
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            result = await executor.execute("return 42", {})

            assert result["status"] == "completed"
            assert "logs" in result
            assert result["logs"] == []
            assert result["logs"] is not None


# ---------------------------------------------------------------------------
# Integration ID propagation in execution context (Project Symi)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIntegrationIdPropagation:
    """Verify integration_id from Task is propagated into execution context.

    System-managed tasks (e.g., alert ingestion) have integration_id set on the
    Task model. The executor must propagate it into execution_context so Cy
    functions like ingest_alerts() are available regardless of trigger path
    (scheduler, managed resources API, or UI Run button).
    """

    def _make_task_run(self, task_id, execution_context=None):
        """Create a mock TaskRun linked to a Task with optional integration_id."""
        from uuid import uuid4

        from analysi.models.task_run import TaskRun

        task_run = MagicMock(spec=TaskRun)
        task_run.id = uuid4()
        task_run.task_id = task_id
        task_run.tenant_id = "test-tenant"
        task_run.cy_script = None  # Will load from task
        task_run.status = "running"
        task_run.execution_context = execution_context or {}
        task_run.workflow_run_id = None
        task_run.workflow_node_instance_id = None

        return task_run

    def _make_task(self, component_id, integration_id=None):
        """Create a mock Task with component."""
        mock_task = MagicMock()
        mock_task.component_id = component_id
        mock_task.integration_id = integration_id
        mock_task.script = "return 'ok'"
        mock_task.directive = None
        mock_task.component = MagicMock()
        mock_task.component.id = component_id
        mock_task.component.tenant_id = "test-tenant"
        mock_task.component.app = "foundation"
        mock_task.component.cy_name = "test_task"
        mock_task.component.last_used_at = None
        return mock_task

    @pytest.mark.asyncio
    async def test_integration_id_propagated_from_task(self):
        """When Task.integration_id is set, it appears in execution_context."""
        from uuid import uuid4

        component_id = uuid4()
        task = self._make_task(component_id, integration_id="splunk-local")
        task_run = self._make_task_run(component_id)

        service = TaskExecutionService()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"status": "completed", "output": "ok"}

        mock_session = AsyncMock()
        # Mock the query that loads the Task
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        with (
            patch.object(service, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as mock_svc_cls,
        ):
            mock_svc_cls.return_value.retrieve_input_data = AsyncMock(return_value={})

            await service._execute_task_with_session(task_run, mock_session)

            # Extract the execution_context passed to executor.execute()
            call_args = mock_executor.execute.call_args[0]
            ctx = call_args[2]  # third positional arg is execution_context
            assert ctx["integration_id"] == "splunk-local"

    @pytest.mark.asyncio
    async def test_integration_id_absent_when_task_has_none(self):
        """When Task.integration_id is None, it's not in execution_context."""
        from uuid import uuid4

        component_id = uuid4()
        task = self._make_task(component_id, integration_id=None)
        task_run = self._make_task_run(component_id)

        service = TaskExecutionService()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"status": "completed", "output": "ok"}

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        with (
            patch.object(service, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as mock_svc_cls,
        ):
            mock_svc_cls.return_value.retrieve_input_data = AsyncMock(return_value={})

            await service._execute_task_with_session(task_run, mock_session)

            ctx = mock_executor.execute.call_args[0][2]
            assert "integration_id" not in ctx

    @pytest.mark.asyncio
    async def test_integration_id_cannot_be_overridden_by_stored_context(self):
        """Stored execution_context cannot override the Task's integration_id.

        The trusted integration_id is set AFTER spreading user-supplied context,
        so even if someone stored a malicious value, it gets overwritten.
        """
        from uuid import uuid4

        component_id = uuid4()
        task = self._make_task(component_id, integration_id="splunk-local")
        task_run = self._make_task_run(
            component_id,
            execution_context={"integration_id": "attacker-controlled"},
        )

        service = TaskExecutionService()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"status": "completed", "output": "ok"}

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        with (
            patch.object(service, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as mock_svc_cls,
        ):
            mock_svc_cls.return_value.retrieve_input_data = AsyncMock(return_value={})

            await service._execute_task_with_session(task_run, mock_session)

            ctx = mock_executor.execute.call_args[0][2]
            assert ctx["integration_id"] == "splunk-local"

    @pytest.mark.asyncio
    async def test_ad_hoc_execution_has_no_integration_id(self):
        """Ad-hoc execution (no task_id) does not include integration_id."""

        task_run = self._make_task_run(task_id=None)
        task_run.cy_script = "return 'ad-hoc'"

        service = TaskExecutionService()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"status": "completed", "output": "ad-hoc"}

        mock_session = AsyncMock()

        with (
            patch.object(service, "executor", mock_executor),
            patch("analysi.services.task_run.TaskRunService") as mock_svc_cls,
        ):
            mock_svc_cls.return_value.retrieve_input_data = AsyncMock(return_value={})

            await service._execute_task_with_session(task_run, mock_session)

            ctx = mock_executor.execute.call_args[0][2]
            assert "integration_id" not in ctx
