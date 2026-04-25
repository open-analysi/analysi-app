"""Comprehensive tests for Round 15 security fixes.

Covers:
1. Info disclosure: routers must not leak internal errors via HTTPException.detail
2. Tenant isolation: repository queries must support tenant_id filtering
3. Safe deserialization: ast.literal_eval replaced with json.loads
4. Safe job parsing: pickle.loads replaced with ARQ Job API
5. Workflow execution context sanitization
6. json.loads correctness
"""

import json
import pathlib

import pytest

# ---------------------------------------------------------------------------
# 1. Info disclosure — routers must return static error messages
# ---------------------------------------------------------------------------


class TestWorkflowsInfoDisclosure:
    """Verify workflows.py error handlers don't leak SQLAlchemy details."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "routers"
            / "workflows.py"
        )
        return path.read_text()

    def test_no_fstring_integrity_error_in_detail(self, source):
        """HTTPException detail must not contain f-string with error_str."""
        # The vulnerable patterns were:
        #   detail=f"Invalid foreign key reference: {error_str}"
        #   detail=f"Integrity error: {error_str}"
        assert 'detail=f"Invalid foreign key reference: {error_str}"' not in source
        assert 'detail=f"Integrity error: {error_str}"' not in source

    def test_uses_static_messages(self, source):
        """IntegrityError handler must use static messages."""
        assert '"Invalid reference in workflow node"' in source
        assert '"Database integrity constraint violated"' in source


class TestIntegrationsInfoDisclosure:
    """Verify integrations.py error handlers don't leak internals."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "routers"
            / "integrations.py"
        )
        return path.read_text()

    def test_connector_not_found_no_resource_enumeration(self, source):
        """404 for missing connector must not echo the connector/integration names."""
        assert 'f"Connector {connector_type}' not in source

    def test_enqueue_failure_no_exception_leak(self, source):
        """Failed enqueue must not expose str(e) in run_details."""
        assert 'f"Failed to enqueue job: {str(e)}"' not in source

    def test_credential_association_static_error(self, source):
        """Credential association failure must use generic message."""
        assert "Credential created but failed" not in source

    def test_logger_uses_percent_formatting(self, source):
        """Logger calls should use %s formatting, not f-strings with sensitive data."""
        # Check the specific problematic f-string logger patterns are gone
        assert 'f"Could not fetch credential for {integration_id}: {e}"' not in source
        assert 'f"Failed to enqueue connector job: {e}"' not in source


class TestTasksInfoDisclosure:
    """Verify tasks.py error handlers don't leak internals."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "routers"
            / "tasks.py"
        )
        return path.read_text()

    def test_create_task_no_exception_in_detail(self, source):
        """create_task ValueError handler must not expose str(e) in detail."""
        assert 'detail={"error": str(e)}' not in source

    def test_analyze_script_no_raw_syntax_error(self, source):
        """_analyze_script must not expose raw SyntaxError message."""
        assert "errors=[str(e)]" not in source


class TestTaskAssistInfoDisclosure:
    """Verify task_assist.py error handlers don't leak internals."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "routers"
            / "task_assist.py"
        )
        return path.read_text()

    def test_autocomplete_no_str_exc_in_detail(self, source):
        """Autocomplete ValueError handler must not use detail=str(exc)."""
        assert "detail=str(exc)" not in source

    def test_autocomplete_uses_static_message(self, source):
        """Autocomplete should return a static error message."""
        assert '"Autocomplete service not configured"' in source


# ---------------------------------------------------------------------------
# 2. Tenant isolation — repository queries must support tenant_id filter
# ---------------------------------------------------------------------------


class TestAlertRepositoryTenantIsolation:
    """Verify reconciliation queries accept and use tenant_id filtering."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "repositories"
            / "alert_repository.py"
        )
        return path.read_text()

    def test_find_paused_accepts_tenant_id(self, source):
        """find_paused_at_workflow_builder must accept tenant_id parameter."""
        assert (
            "def find_paused_at_workflow_builder(\n        self, tenant_id:" in source
        )

    def test_find_stuck_accepts_tenant_id(self, source):
        """find_stuck_running_alerts must accept tenant_id parameter."""
        assert "tenant_id: str | None = None" in source
        # Verify the method uses it
        assert "conditions.append(Alert.tenant_id == tenant_id)" in source

    def test_find_mismatched_accepts_tenant_id(self, source):
        """find_mismatched_alert_statuses must accept tenant_id parameter."""
        # Check the method signature
        lines = source.splitlines()
        in_method = False
        has_tenant_param = False
        for line in lines:
            if "def find_mismatched_alert_statuses(" in line:
                in_method = True
            if in_method and "tenant_id: str | None" in line:
                has_tenant_param = True
                break
            if in_method and "def " in line and "find_mismatched" not in line:
                break
        assert has_tenant_param, (
            "find_mismatched_alert_statuses missing tenant_id parameter"
        )

    def test_find_orphaned_accepts_tenant_id(self, source):
        """find_orphaned_running_analyses must accept tenant_id parameter."""
        lines = source.splitlines()
        in_method = False
        has_tenant_param = False
        for line in lines:
            if "def find_orphaned_running_analyses(" in line:
                in_method = True
            if in_method and "tenant_id: str | None" in line:
                has_tenant_param = True
                break
            if in_method and "def " in line and "find_orphaned" not in line:
                break
        assert has_tenant_param, (
            "find_orphaned_running_analyses missing tenant_id parameter"
        )


class TestAlertAnalysisRepoTenantIsolation:
    """Verify AlertAnalysisRepository mutation methods accept tenant_id."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "repositories"
            / "alert_repository.py"
        )
        return path.read_text()

    def test_update_step_progress_accepts_tenant_id(self, source):
        """update_step_progress must accept tenant_id parameter."""
        lines = source.splitlines()
        in_method = False
        has_tenant_param = False
        for line in lines:
            if "def update_step_progress(" in line:
                in_method = True
            if in_method and "tenant_id: str | None" in line:
                has_tenant_param = True
                break
            if (
                in_method
                and line.strip().startswith("def ")
                and "update_step_progress" not in line
            ):
                break
        assert has_tenant_param, "update_step_progress missing tenant_id parameter"

    def test_mark_completed_accepts_tenant_id(self, source):
        """mark_completed must accept tenant_id parameter."""
        lines = source.splitlines()
        in_method = False
        has_tenant_param = False
        for line in lines:
            if "def mark_completed(" in line:
                in_method = True
            if in_method and "tenant_id: str | None" in line:
                has_tenant_param = True
                break
            if (
                in_method
                and line.strip().startswith("def ")
                and "mark_completed" not in line
            ):
                break
        assert has_tenant_param, "mark_completed missing tenant_id parameter"

    def test_increment_retry_accepts_tenant_id(self, source):
        """increment_workflow_gen_retry_count must accept tenant_id parameter."""
        lines = source.splitlines()
        in_method = False
        has_tenant_param = False
        for line in lines:
            if "def increment_workflow_gen_retry_count(" in line:
                in_method = True
            if in_method and "tenant_id: str | None" in line:
                has_tenant_param = True
                break
            if (
                in_method
                and line.strip().startswith("def ")
                and "increment_workflow" not in line
            ):
                break
        assert has_tenant_param, (
            "increment_workflow_gen_retry_count missing tenant_id parameter"
        )


# ---------------------------------------------------------------------------
# 3. Safe deserialization — no ast.literal_eval on untrusted data
# ---------------------------------------------------------------------------


class TestNoAstLiteralEval:
    """Verify ast.literal_eval is not used on external/untrusted data."""

    def _read_src(self, *parts):
        path = pathlib.Path(__file__).resolve().parents[3] / "src" / "analysi"
        for p in parts:
            path = path / p
        return path.read_text()

    def test_cy_alert_functions_no_ast_literal_eval(self):
        """cy_alert_functions must NOT use ast.literal_eval.

        Post-Skaros: the function returns OCSF columns directly from the
        ORM model without any string parsing, so json.loads is also absent.
        """
        source = self._read_src("services", "cy_alert_functions.py")
        assert "ast.literal_eval" not in source

    def test_task_execution_uses_native_api_no_ast_literal_eval(self):
        """task_execution uses run_native_async (Cy 0.38+) — no string
        parsing needed.  ast.literal_eval must NOT be present.
        """
        source = self._read_src("services", "task_execution.py")
        assert "run_native_async" in source
        # Cy 0.38+: run_native_async returns Python objects directly.
        # ast.literal_eval is no longer needed or allowed.
        assert "ast.literal_eval" not in source

    def test_no_ast_literal_eval_in_src(self):
        """No source file should use ast.literal_eval (blanket check).

        Cy 0.38+ uses run_native_async() which returns Python objects directly,
        so no file needs ast.literal_eval anymore.
        """
        src_root = pathlib.Path(__file__).resolve().parents[3] / "src"
        violations = []
        for py_file in src_root.rglob("*.py"):
            rel = str(py_file.relative_to(src_root))
            content = py_file.read_text()
            if "ast.literal_eval" in content:
                violations.append(rel)
        assert not violations, f"ast.literal_eval found in: {violations}"


# ---------------------------------------------------------------------------
# 4. Safe job parsing — no raw pickle.loads on Redis data
# ---------------------------------------------------------------------------


class TestNoRawPickle:
    """Verify queue_cleanup.py does not use raw pickle.loads."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "alert_analysis"
            / "queue_cleanup.py"
        )
        return path.read_text()

    def test_no_pickle_loads(self, source):
        """queue_cleanup must not use pickle.loads (unsafe deserialization)."""
        assert "pickle.loads" not in source

    def test_no_pickle_import(self, source):
        """queue_cleanup should not import pickle at all."""
        assert "import pickle" not in source

    def test_uses_arq_job_api(self, source):
        """queue_cleanup should use ARQ's Job API for safe deserialization."""
        assert "from arq.jobs import Job" in source
        assert "Job(job_id" in source
        assert "await job.info()" in source


# ---------------------------------------------------------------------------
# 5. Workflow execution context sanitization
# ---------------------------------------------------------------------------


class TestWorkflowExecutionContextSanitization:
    """Verify workflow_execution.py sanitizes execution_context."""

    @pytest.fixture
    def source(self):
        path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src"
            / "analysi"
            / "services"
            / "workflow_execution.py"
        )
        return path.read_text()

    def test_imports_sanitizer(self, source):
        """workflow_execution must import sanitize_execution_context."""
        assert (
            "from analysi.auth.context_sanitizer import sanitize_execution_context"
            in source
        )

    def test_calls_sanitize(self, source):
        """workflow_execution must call sanitize_execution_context."""
        assert "sanitize_execution_context(execution_context)" in source


# ---------------------------------------------------------------------------
# 6. json.loads correctness — verify json.loads handles expected formats
# ---------------------------------------------------------------------------


class TestJsonLoadsCompatibility:
    """Verify json.loads handles the data formats previously handled by ast.literal_eval."""

    def test_dict_string_parsed(self):
        """JSON dict string is correctly parsed."""
        data = '{"key": "value", "count": 42}'
        result = json.loads(data)
        assert result == {"key": "value", "count": 42}

    def test_list_string_parsed(self):
        """JSON list string is correctly parsed."""
        data = "[1, 2, 3]"
        result = json.loads(data)
        assert result == [1, 2, 3]

    def test_nested_structure_parsed(self):
        """Nested JSON structure is correctly parsed."""
        data = '{"results": [{"ip": "1.2.3.4", "score": 0.9}]}'
        result = json.loads(data)
        assert result["results"][0]["ip"] == "1.2.3.4"

    def test_python_repr_rejected(self):
        """Python repr format (True/False/None) must fail with json.loads.

        This is a feature, not a bug: ast.literal_eval accepted Python-specific
        literals that could be part of code injection payloads.
        """
        # Python repr uses True/False/None (capitalized)
        python_repr = "{'key': True, 'value': None}"
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(python_repr)

    def test_tuple_repr_rejected(self):
        """Python tuple repr must fail with json.loads (attack surface reduction)."""
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads("(1, 2, 3)")
